import falcon
from google.cloud.logging.handlers import ContainerEngineHandler
from ib_insync import IB
import logging


# setup logging
logger = logging.getLogger('ib-gw.healthcheck')
logger.setLevel(logging.DEBUG)
logger.addHandler(ContainerEngineHandler())

# instantiate ib-insync IB gateway
ib_gw = IB()


class HealthCheck:

    def __init__(self):
        logger.info('IB Gateway healthcheck is active.')

    @staticmethod
    def on_get(_, response):
        try:
            ib_gw.connect('localhost', 4003, 999)

            if ib_gw.isConnected() and ib_gw.client.isReady():
                logger.info('IB Gateway healthcheck succeded.')
                logger.info(ib_gw.client.connectionStats())
                response.body = '{"connState": "{' + str(ib_gw.client.connState) + '}", "currentTime": "{' + ib_gw.reqCurrentTime().isoformat() + '}"}'
                response.status = falcon.HTTP_200
            else:
                logger.warning('IB Gateway healthcheck failed.')
                response.body = '{"connState": "{' + str(ib_gw.client.connState) + '}"}'
                response.status = falcon.HTTP_503
        except Exception as e:
            logger.warning('IB Gateway healthcheck failed.')
            logger.error(e)
            response.body = '{"connState": "{' + str(ib_gw.client.connState) + '}", "error": "{' + str(e) + '}"}'
            response.status = falcon.HTTP_503
        finally:
            ib_gw.disconnect()


api = falcon.API()
api.add_route('/', HealthCheck())
