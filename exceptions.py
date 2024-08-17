class NoEnvVarsError(Exception):

    def __str__(self):
        return 'Не обнаружены все необходимые переменные окружения'


class RequestToApiError(Exception):
    pass
