from ib_insync import IB, IBC, util
import logging


util.logToConsole()


class IBGW(IB):

    def __init__(self, ibc_config, ib_config={}, connection_timeout=60):
        self.ibc_config = ibc_config
        self.ib_config = {'host': '127.0.0.1', 'port': 4001, 'clientId': 1, **ib_config}
        self.connection_timeout = connection_timeout

        self.ibc = IBC(**self.ibc_config)
        super().__init__()

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
                IB.sleep(1)
                wait -= 1
                logging.info('Connecting to IB gateway...')
                try:
                    self.connect(**self.ib_config)
                except ConnectionRefusedError:
                    if not wait:
                        logging.warning('Timeout reached')
                        raise TimeoutError('Could not connect to IB gateway')
        except Exception as e:
            logging.error(e)
            # write the launch log to logging (of limited use though as only the first
            # phase of the gateway startup process is logged in this non-encrypted log)
            try:
                with open(self.ibc_config['twsPath'] + '/launcher.log', 'r') as fp:
                    logging.info(fp.read())
            except FileNotFoundError:
                logging.warning(self.ibc_config['twsPath'] + '/launcher.log not found')
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
        logging.info('Done.')
