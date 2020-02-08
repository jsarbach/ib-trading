from datetime import datetime, timedelta
from ib_insync import Future, Index
import logging
from math import isnan, sqrt


CONTRACT_SPECS = {
    'VX': {
        'months': ['F', 'G', 'H', 'J', 'K', 'M', 'N', 'Q', 'U', 'V', 'X', 'Z'],
        'exchange': 'CFE',
        'currency': 'USD'
    },
    'MES': {
        'months': ['H', 'M', 'U', 'Z'],
        'exchange': 'GLOBEX',
        'currency': 'USD'
    }
}
PROTOTYPE = [0.170460003, 0.066938643, 0.004149764, -0.033933616, -0.057032353, -0.071042446, -0.079539997]


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


def get_prices(ib_gw, contracts=()):
    logging.info('Requesting tick data for {}...'.format(contracts))
    return [ticker.close if not isnan(ticker.close) else ticker.last for ticker in ib_gw.reqTickers(*contracts)]


def main(ib_gw):
    ib_gw.reqMarketDataType(3)

    vx = get_contracts(ib_gw, 'VX', 6)
    prices = get_prices(ib_gw, [Index(symbol='VIX', exchange='CBOE', currency='USD')] + vx)
    logging.debug('Prices: {}'.format(prices))
    es = get_contracts(ib_gw, 'MES', 1)
    # logging.info(es)

    try:
        features = [p / prices[0] for p in prices]
    except ZeroDivisionError as e:
        raise ZeroDivisionError('{} - prices: {}'.format(e, prices))
    logging.debug('Features: {}'.format(features))
    features_mean = sum(features) / len(features)
    features_demeaned = [f - features_mean for f in features]
    logging.debug('Features demeaned: {}'.format(features_demeaned))

    mse = [sqrt(sum([(f - i * p) ** 2 for f, p in zip(features_demeaned, PROTOTYPE)])) for i in range(-1, 2)]
    logging.debug('MSE: {}'.format(mse))
    signal = (mse[2] == min(mse)) - (mse[0] == min(mse))
    logging.debug('Signal: {}'.format(signal))

    allocation = {
        vx[0].conId: 1/3 * signal,
        es[0].conId: 2/3 * signal
    }
    logging.debug('Allocation: {}'.format(allocation))
    return allocation


if __name__ == '__main__':
    from ib_insync import IB
    ib = IB()
    ib.connect('localhost', 4001, 1)
    try:
        print(main(ib))
    finally:
        ib.disconnect()
