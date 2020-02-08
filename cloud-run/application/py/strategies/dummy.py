from datetime import datetime, timedelta
from ib_insync import Future
import logging
from random import randint


CONTRACT_SPECS = {
    'MNQ': {
        'months': ['H', 'M', 'U', 'Z'],
        'exchange': 'GLOBEX',
        'currency': 'USD'
    }
}


def get_contracts(ib_gw, series, n):
    contract_years = [str(datetime.now().year + i)[-1] for i in range(2)]
    contract_symbols = [series + m + y for y in contract_years for m in CONTRACT_SPECS[series]['months']]

    logging.info('Requesting contract details for {}...'.format(contract_symbols))
    contract_details = {}
    for symbol in contract_symbols:
        cd = ib_gw.reqContractDetails(Future(localSymbol=symbol,
                                             exchange=CONTRACT_SPECS[series]['exchange'],
                                             currency=CONTRACT_SPECS[series]['currency']))
        contract_details[symbol] = cd[0].contract if len(cd) > 0 else None

    contracts = {k: v for k, v in contract_details.items()
                 if v is not None and v.lastTradeDateOrContractMonth > (datetime.now() + timedelta(days=6)).strftime('%Y%m%d')}

    return [contracts[k] for k in [k for k in contract_symbols if k in contracts.keys()][:n]]


def main(ib_gw):
    ib_gw.reqMarketDataType(3)

    mnq = get_contracts(ib_gw, 'MNQ', 1)

    allocation = {
        mnq[0].conId: randint(-1, 1)
    }
    logging.debug('Allocation: {}'.format(allocation))
    return allocation


if __name__ == '__main__':
    from ib_insync import IB
    ib = IB()
    ib.connect('localhost', 4001, 1)
    try:
        print(main(ib))
    except Exception as e:
        raise e
    finally:
        ib.disconnect()
