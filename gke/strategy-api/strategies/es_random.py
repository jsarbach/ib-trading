from datetime import datetime, timedelta
from google.cloud.logging.handlers import ContainerEngineHandler
from ib_insync import IB, Future
import logging
from math import isnan
from os import environ
from random import randint


# setup logging
module_logger = logging.getLogger('strategy-api.es-random')
module_logger.setLevel(logging.DEBUG)
module_logger.addHandler(ContainerEngineHandler())

# get environment variables
GATEWAY = environ.get('GATEWAY', default='ib-gw-paper')
# define specs of contracts used
CONTRACT_SPECS = {
    'ES': {
        'months': ['H', 'M', 'U', 'Z'],
        'exchange': 'GLOBEX',
        'currency': 'USD'
    }
}

# instantiate ib-insync IB gateway
ib_gw = IB()


def get_contracts(series, n):
    """
    Requests contract details for a series of futures

    :param series: ticker symbol (str)
    :param n: number of consecutive contracts (int)
    :return: list of Contract
    """
    contract_years = [str(datetime.now().year + i)[-1] for i in range(2)]
    contract_symbols = [series + m + y for y in contract_years for m in CONTRACT_SPECS[series]['months']]

    module_logger.info('Requesting contract details for {}...'.format(contract_symbols))
    contract_details = {}
    for symbol in contract_symbols:
        cd = ib_gw.reqContractDetails(Future(localSymbol=symbol,
                                             exchange=CONTRACT_SPECS[series]['exchange'],
                                             currency=CONTRACT_SPECS[series]['currency']))
        contract_details[symbol] = cd[0].contract if len(cd) > 0 else None

    contracts = {
        k: v for k, v in contract_details.items()
        # roll over 6 days prior to expiry
        if v is not None and v.lastTradeDateOrContractMonth > (datetime.now() + timedelta(days=6)).strftime('%Y%m%d')
    }

    return [contracts[k] for k in [k for k in contract_symbols if k in contracts.keys()][:n]]


def get_prices(contracts=()):
    """
    Requests last available price for contracts

    :param contracts: iterable of Contract
    :return: list of prices
    """
    module_logger.info('Requesting tick data for {}...'.format(contracts))
    return [ticker.close if not isnan(ticker.close) else ticker.last for ticker in ib_gw.reqTickers(*contracts)]


def main():
    """
    Pseudo strategy that randomly goes long or short the E-mini S&P 500 Futures

    :return: allocation/strategy signal (dict)
    """
    ib_gw.connect(GATEWAY, 4003, 1)

    # get front month ES contract (E-mini S&P 500 Futures)
    es = get_contracts('ES', 1)
    # prices = get_prices(es)
    # module_logger.debug('Prices: {}'.format(prices))

    ib_gw.disconnect()

    # random long (+1), short (-1) or neutral (0)
    # obviously just for illustration purposes - don't do this ;-)
    signal = randint(-1, 1)

    allocation = {
        es[0].conId: signal
    }
    module_logger.debug('Allocation: {}'.format(allocation))
    return allocation


if __name__ == '__main__':
    main()
