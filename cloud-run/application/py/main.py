from base64 import b64decode
from datetime import datetime
import falcon
from googleapiclient.discovery import build
from importlib import import_module
import json
import logging
from os import environ, listdir
import re
from time import sleep

from lib.ibgw import IBGW


# get environment variables
INTENT = environ.get('INTENT')
TWS_INSTALL_LOG = environ.get('TWS_INSTALL_LOG')
# set constants
SECRET_RESOURCE = 'projects/[PROJECT_ID]/secrets/ib-credentials_{}_{}/versions/latest'
SECRET_RETRY = 5


class Ping:
    """
    Dummy class to use as a fallback intent; returns time string from IB.
    """

    @classmethod
    def main(cls, ib_gw, _):
        return {
            'currentTime': ib_gw.reqCurrentTime().isoformat()
        }


def get_secret(trading_mode, name):
    """
    Requests IB credentials from Secret Manager.

    :param trading_mode: IB trading mode (paper/live) (str)
    :param name: name of secret (userid/password) (str)
    :return: secret value (str)
    """

    response = None
    wait = SECRET_RETRY
    while response is None:
        try:
            response = service.projects().secrets().versions().access(
                name=SECRET_RESOURCE.format(trading_mode, name)).execute()
        except Exception as e:
            if wait:
                logging.warning('Couldn\'t fetch {}, retrying... ({})'.format(name, e))
                sleep(2 ** (SECRET_RETRY - wait))
                wait -= 1
            else:
                raise e

    return b64decode(response['payload']['data']).decode()


# import intent module
if INTENT is not None:
    intent = import_module('intents.' + INTENT)
else:
    logging.warning('INTENT not set')
    intent = Ping()

# build IBC config from environment variables
env = {
    key: environ.get(key) for key in
    ['ibcIni', 'ibcPath', 'javaPath', 'twsPath', 'twsSettingsPath']
}
env['javaPath'] += '/{}/bin'.format(listdir(env['javaPath'])[0])
with open(TWS_INSTALL_LOG, 'r') as fp:
    install_log = fp.read()
ibc_config = {
    'gateway': True,
    'twsVersion': re.search('IB Gateway ([0-9]{3})', install_log).group(1),
    **env
}
logging.debug(ibc_config)

# build Secret Manager service
service = build('secretmanager', 'v1beta1', cache_discovery=False)


class Main:
    """
    Main route.
    """

    def on_get(self, request, response, trading_mode):
        self._on_request(request, response, trading_mode)

    def on_post(self, request, response, trading_mode):
        body = json.load(request.stream) if request.content_length else {}
        self._on_request(request, response, trading_mode, **body)

    @staticmethod
    def _on_request(_, response, trading_mode, **body):
        """
        Handles HTTP request.

        :param _: Falcon request (not used)
        :param response: Falcon response
        :param trading_mode: IB trading mode (paper/live) (str)
        :param body: HTTP request body (dict)
        """

        if trading_mode in ['live', 'paper']:
            try:
                # get secrets and update config
                ib_credentials = {
                    secret: get_secret(trading_mode, secret)
                    for secret in ['userid', 'password']
                }
                config = {
                    **ibc_config,
                    'tradingMode': trading_mode,
                    **ib_credentials
                }
                logging.info({**config, 'password': 'xxx'})

                # instantiate IB gateway, connect, and call intent
                ib_gw = IBGW(config)
                try:
                    ib_gw.start_and_connect()

                    retval = intent.main(ib_gw, trading_mode, **body)
                    response.status = falcon.HTTP_200
                except Exception as e:
                    raise e
                finally:
                    ib_gw.stop_and_terminate()
            except Exception as e:
                error_str = '{}: {}'.format(e.__class__.__name__, e)
                logging.error(error_str)
                retval = {'error': error_str}
                response.status = falcon.HTTP_500
        else:
            logging.warning('Trading mode unset or invalid')
            retval = {}
            response.status = falcon.HTTP_200

        retval['utcTimestamp'] = datetime.utcnow().isoformat()
        # logging.debug(retval)
        response.content_type = falcon.MEDIA_JSON
        response.body = json.dumps(retval)


# instantiante Falcon API and define route for /paper and /live
api = falcon.API()
api.add_route('/{trading_mode}', Main())
