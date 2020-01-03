import falcon
from google.cloud.logging.handlers import ContainerEngineHandler
from importlib import import_module
import json
import logging
from os import environ


# setup logging
main_logger = logging.getLogger('strategy-api.main')
main_logger.setLevel(logging.DEBUG)
main_logger.addHandler(ContainerEngineHandler())

# get environment variables
STRATEGY = environ.get('STRATEGY')

# import strategy module
strategy_module = import_module('strategies.' + STRATEGY) if STRATEGY is not None else None


class HealthCheck:

    def __init__(self):
        main_logger.info('Strategy API healthcheck is active.')

    @staticmethod
    def on_get(_, response):
        main_logger.info('Strategy API healthcheck succeded.')
        response.status = falcon.HTTP_200
        response.body = '{"status": "ok"}'


class Main:

    @staticmethod
    def on_get(_, response):
        try:
            retval = strategy_module.main()
            response.status = falcon.HTTP_200
        except Exception as e:
            main_logger.error(e)
            retval = {}
            response.status = falcon.HTTP_500
        response.body = json.dumps(retval)


api = falcon.API()
api.add_route('/', Main())
api.add_route('/health', HealthCheck())
