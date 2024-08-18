import logging
import os
import sys
import time
from http import HTTPStatus
from logging import Formatter, StreamHandler

import requests
from dotenv import load_dotenv
from telebot import apihelper, TeleBot

from exceptions import NoEnvVarsError, RequestToApiError

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = StreamHandler(stream=sys.stdout)
handler.setFormatter(
    Formatter(
        '%(asctime)s [%(levelname)s] %(message)s '
        'Место вызова: %(funcName)s, строка: %(lineno)d'
    )
)
logger.addHandler(handler)


def check_tokens():
    """Проверка доступности переменных окружения."""
    source = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')
    undefined_vars = ()
    for token in source:
        if not globals().get(token):
            undefined_vars += (token,)
    if undefined_vars:
        logger.critical(
            'Отсутствуют обязательные переменные окружения: '
            f'{str(undefined_vars)[1:-1]}. '
            'Программа принудительно остановлена.'
        )
        raise NoEnvVarsError


def send_message(bot, message):
    """Отправка сообщения в Telegram-чат."""
    logger.debug(
        f'Запуск процесса отправки сообщения "{message}".'
    )
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except (apihelper.ApiException, requests.RequestException):
        logger.exception(
            f'Не удалось отправить сообщение "{message}".'
        )
    else:
        logger.debug(f'Бот отправил сообщение "{message}".')


def get_api_answer(timestamp):
    """
    Отправка запроса к эндпоинту API-сервиса.
    В случае успеха возвращает ответ API, приведя его к типам данных Python.
    """
    params = {'from_date': timestamp}
    logger.debug(
        'Запуск процесса отправки запроса к эндпоинту '
        f'{ENDPOINT}. Параметры запроса: {params}.'
    )
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
    except requests.RequestException:
        raise ConnectionError(
            'Ошибка отправки запроса к эндпоинту '
            f'{ENDPOINT}. Параметры запроса: {params}.'
        )
    else:
        if response.status_code != HTTPStatus.OK:
            raise RequestToApiError(
                f'Ошибка запроса к эндпоинту {ENDPOINT}. '
                f'Причина: {response.reason}. '
                f'Код ответа API: {response.status_code}.'
            )
        logger.debug(
            'Успешное завершение отправки запроса к эндпоинту '
            f'{ENDPOINT}. Параметры запроса: {params}.'
        )
        return response.json()


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    logger.debug('Запуск проверки ответа API.')
    if not isinstance(response, dict):
        raise TypeError(
            'Ошибка типа возвращаемых данных. '
            f'Полученный тип данных: {type(response)}. '
            'Ожидаемый тип данных: dict. '
        )
    elif 'homeworks' not in response:
        raise KeyError(
            'В ответе API отсутствует ожидаемый ключ "homeworks".'
        )
    elif not isinstance(response['homeworks'], list):
        raise TypeError(
            'Ошибка типа полученных данных под ключом "homeworks". '
            f'Полученный тип данных: {type(response["homeworks"])}. '
            'Ожидаемый тип данных: list.'
        )
    logger.debug('Успешное завершение проверки ответа API.')


def parse_status(homework):
    """
    Извлечение из информации о конкретной домашней работе статуса этой работы.
    В случае успеха возвращает подготовленную для отправки в Telegram строку.
    """
    logger.debug('Запуск проверки статуса домашней работы.')
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')

    if 'homework_name' not in homework:
        raise KeyError('В ответе API нет ключа "homework_name".')
    elif 'status' not in homework:
        raise KeyError('В ответе API нет ключа "status".')
    elif homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            'В ответе API неожиданный статус домашней работы: '
            f'{homework_status}.'
        )
    verdict = HOMEWORK_VERDICTS[homework_status]
    logger.debug(
        'Успешное завершение проверки статуса домашней работы.'
    )
    return (
        f'Изменился статус проверки работы "{homework_name}". '
        f'{verdict}'
    )


def main():
    """Основная логика работы бота."""
    check_tokens()

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    current_error_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)

            if response['homeworks']:
                message = parse_status(response['homeworks'][0])
                send_message(bot, message)
                current_error_message = ''
            else:
                logger.debug(
                    'Новые статусы домашних работ отсутствуют.'
                )
            timestamp = response.get('current_date', int(time.time()))
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if current_error_message != message:
                send_message(bot, message)
            current_error_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
