from ib_insync import IB, IBC

from lib.gcp import logger as logging


class IBGW(IB):

    IB_CONFIG = {'host': '127.0.0.1', 'port': 4001, 'clientId': 1}

    def __init__(self, ibc_config, ib_config=None, connection_timeout=60, timeout_sleep=5):
        super().__init__()
        ib_config = ib_config or {}
        self.ibc_config = ibc_config
        self.ib_config = {**self.IB_CONFIG, **ib_config}
        self.connection_timeout = connection_timeout
        self.timeout_sleep = timeout_sleep

        self.ibc = IBC(**self.ibc_config)

    def start_and_connect(self):
        """
        Starts the IB gateway with IBC and connects to it.
        """

        logging.info('Starting IBC...')
        self.ibc.start()
        wait = self.connection_timeout

        try:
            while not self.isConnected():
                # retry until connection is established or timeout is reached
                self.sleep(self.timeout_sleep)
                wait -= self.timeout_sleep
                logging.info('Connecting to IB gateway...')
                try:
                    self.connect(**self.ib_config)
                except ConnectionRefusedError:
                    if wait <= 0:
                        logging.warning('Timeout reached')
                        raise TimeoutError('Could not connect to IB gateway')
            logging.info('Connected.')
        except Exception as e:
            logging.error(f'{e.__class__.__name__}: {e}')
            # write the launch log to logging (of limited use though as only the first
            # phase of the gateway startup process is logged in this non-encrypted log)
            try:
                with open(f"{self.ibc_config['twsPath']}/launcher.log", 'r') as fp:
                    logging.info(fp.read())
            except FileNotFoundError:
                logging.warning(f"{self.ibc_config['twsPath']}/launcher.log not found")
            raise e

    def stop_and_terminate(self, wait=0):
        """
        Closes the connection with the IB gateway and terminates it.

        :param wait: seconds to wait after terminating (int)
        """

        logging.info('Disconnecting from IB gateway...')
        self.disconnect()
        logging.info('Terminating IBC...')
        self.ibc.terminate()
        self.sleep(wait)
