import logging
import os
import sys
import time
from logging import Formatter, StreamHandler

import requests
from dotenv import load_dotenv
from telebot import TeleBot

from exceptions import NoEnvVarsError, RequestError

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
    Formatter('%(asctime)s [%(levelname)s] %(message)s')
)
logger.addHandler(handler)


def check_tokens():
    """Проверка доступности переменных окружения."""
    if not PRACTICUM_TOKEN:
        logger.critical(
            'Отсутствует обязательная переменная окружения: '
            '"PRACTICUM_TOKEN". Программа принудительно остановлена.'
        )
        raise NoEnvVarsError
    elif not TELEGRAM_TOKEN:
        logger.critical(
            'Отсутствует обязательная переменная окружения: '
            '"TELEGRAM_TOKEN". Программа принудительно остановлена.'
        )
        raise NoEnvVarsError
    elif not TELEGRAM_CHAT_ID:
        logger.critical(
            'Отсутствует обязательная переменная окружения: '
            '"TELEGRAM_CHAT_ID". Программа принудительно остановлена.'
        )
        raise NoEnvVarsError


def send_message(bot, message):
    """Отправка сообщения в Telegram-чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception:
        logger.exception(
            'Не удалось отправить сообщение.'
        )
    else:
        logger.debug(f'Бот отправил сообщение: "{message}".')


def get_api_answer(timestamp):
    """
    Отправка запроса к эндпоинту API-сервиса.
    В случае успеха возвращает ответ API, приведя его к типам данных Python.
    """
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except Exception:
        raise RequestError('Ошибка обращения к API.')
    else:
        if response.status_code == 404:
            raise RequestError(
                f'Эндпоинт {ENDPOINT} недоступен. '
                f'Код ответа API: {response.status_code}.'
            )
        elif response.status_code != 200:
            raise RequestError(
                'Ошибка обращения к API. '
                f'Код ответа API: {response.status_code}.'
            )
        return response.json()


def check_response(response):
    """
    Проверка ответа API на соответствие документации.
    """
    if not isinstance(response, dict):
        raise TypeError('Ошибка типа возвращаемых данных. Ожидается словарь.')
    elif not ('homeworks' in response and 'current_date' in response):
        raise KeyError('В ответе API отсутствуют ожидаемые ключи.')
    elif not isinstance(response['homeworks'], list):
        raise TypeError(
            'Ошибка типа полученных данных под ключом "homeworks". '
            'Ожидается список.'
        )


def parse_status(homework):
    """
    Извлечение из информации о конкретной домашней работе статуса этой работы.
    В случае успеха возвращает подготовленную для отправки в Telegram строку.
    """
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')

    if not homework_name:
        raise KeyError('В ответе API нет ключа "homework_name".')
    elif homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            'В ответе API неожиданный статус домашней работы.'
        )
    elif homework_status:
        verdict = HOMEWORK_VERDICTS[homework_status]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'


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

            timestamp = response['current_date']

            if len(response['homeworks']) > 0:
                for homework in response['homeworks']:
                    if parse_status(homework):
                        message = parse_status(homework)
                        send_message(bot, message)
            logger.debug(
                'Новые статусы домашних работ отсутствуют.'
            )
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if current_error_message != message:
                send_message(bot, message)
            current_error_message = message

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
