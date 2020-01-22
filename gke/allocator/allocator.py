from datetime import datetime, timezone
from google.cloud import firestore_v1 as firestore
from google.cloud.logging.handlers import ContainerEngineHandler
from ib_insync import IB, Contract, Forex, MarketOrder
import json
import logging
from os import environ
import re
import requests


# setup logging
logger = logging.getLogger('allocator')
logger.setLevel(logging.DEBUG)
logger.addHandler(ContainerEngineHandler())

# get environment variables
DRY_RUN = environ.get('DRY_RUN', default=False)
HOSTNAME = environ.get('HOSTNAME')  # Pod name
ORDER_PROPERTIES = environ.get('ORDER_PROPERTIES', default='{}')
STRATEGIES = environ.get('STRATEGIES')
TRADING_MODE = environ.get('TRADING_MODE', default='paper')

# instantiate Firestore Client
db = firestore.Client()

# instantiate ib-insync IB gateway
ib_gw = IB()


def get_account_values(account):
    """
    Requests account values from IB

    :param account: IB account number
    :return: account values (dict)
    """
    account_values = {}
    for item in ib_gw.accountValues(account):
        try:
            value = float(item.value)
        except ValueError:
            value = item.value

        if item.currency == '':
            account_values[item.tag] = value
        else:
            if item.tag not in account_values:
                account_values[item.tag] = {}
            account_values[item.tag][item.currency] = value
    # TODO: use pandas w/ ib_insync.util.df() instead

    return account_values


def get_contract_data(contract_ids=()):
    """
    Requests contract details and price (tick) data

    :param contract_ids: iterable of IB contract IDs
    :return: contract data (dict)
    """
    contract_data = {}
    for con_id in contract_ids:
        contract_details = ib_gw.reqContractDetails(Contract(conId=con_id))[0].nonDefaults()
        contract = contract_details.pop('contract')
        contract_data[con_id] = {
            'contract': contract,
            'contract_details': contract_details,
            'ticker': get_tickers(contract)
        }

    return contract_data


def get_signal(identifier):
    """
    Requests signals from strategy service

    :param identifier: strategy identfier/name (str)
    :return: response from srategy service (dict)
    """
    try:
        response = requests.get('http://{}:8080/'.format(identifier))
        if response.status_code == 200:
            return json.loads(response.content)
        else:
            raise requests.exceptions.RequestException(response.status_code)
    except requests.exceptions.RequestException as e:
        logger.error('Request to service {} returned an exception: {}'.format(identifier, e))
        raise e
        # return {}
    except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
        logger.error('Could not connect to service {}: {}'.format(identifier, e))
        raise e
        # return {}


def get_tickers(contract):
    """
    Requests price (tick) data

    :param contract: ib_insync.Contract
    :return: ib_insync.Ticker
    """
    logging.info('Requesting tick data for {}...'.format(contract.localSymbol))
    return ib_gw.reqTickers(contract)[0]


def make_allocation(signals=()):
    """
    Consolidates all strategy signals into one allocation

    :param signals: (iterable of dict)
    :return: consolidated allocation (dict)
    """
    allocation = {}
    for s in signals:
        for k, v in s.items():
            if k in allocation:
                allocation[k] += v
            else:
                allocation[k] = v

    return allocation


def main():
    # query config
    config = db.collection('config').document('paper' if TRADING_MODE == 'local' else TRADING_MODE).get().to_dict()

    # activity log for Firestore
    activity_log = {
        'agent': (re.match('([\\w-]+)-([0-9]+|manual-[0-9a-z]+)-[0-9a-z]+$', HOSTNAME)).group(1) if HOSTNAME is not None else 'localhost',
        'environment': {'DRY_RUN': DRY_RUN, 'ORDER_PROPERTIES': ORDER_PROPERTIES, 'STRATEGIES': STRATEGIES, 'TRADING_MODE': TRADING_MODE},
        'config': config,
        'exception': None
    }

    main_e = None
    try:
        strategies = STRATEGIES.split(',') if STRATEGIES is not None else []
        gateway = 'localhost' if TRADING_MODE == 'local' else 'ib-gw-' + TRADING_MODE
        order_properties = json.loads(ORDER_PROPERTIES)

        logger.info('Running allocator for {}...'.format(strategies))

        # get signals for all strategies
        signals = {s: get_signal('localhost' if TRADING_MODE == 'local' else s) for s in strategies}
        activity_log['signals'] = signals
        # scale w/ exposure
        scaled_signals = [
            {
                instr: alloc * config['exposure']['strategies'][strat]
                for instr, alloc in sig.items()
            } for strat, sig in signals.items()
        ]
        activity_log['scaledSignals'] = scaled_signals

        # consolidate strategies
        allocation = make_allocation(scaled_signals)
        activity_log['allocation'] = allocation
        logger.info('Allocation: {}'.format(activity_log['allocation']))

        # connect to IB gateway
        ib_gw.connect(gateway, 4003, 1)

        # get net liquidation value
        account_values = get_account_values(config['account'])
        base_currency = list(account_values['NetLiquidation'].keys())[0]
        net_liquidation = float(account_values['NetLiquidation'][base_currency])
        activity_log['netLiquidation'] = net_liquidation

        # get positions
        positions = {item.contract.conId: item.position for item in ib_gw.positions(config['account'])}
        activity_log['positions'] = positions

        # get contract details
        contract_data = get_contract_data(set(list(allocation.keys()) + list(positions.keys())))
        # build contractId->symbol lookup dict
        symbol_map = {k: v['contract'].localSymbol for k, v in contract_data.items()}
        activity_log['contractIds'] = {v['contract'].localSymbol: k for k, v in contract_data.items()}
        # replace dict keys
        activity_log['signals'] = {k: {symbol_map[k]: v for k, v in v.items()} for k, v in signals.items()}
        activity_log['scaledSignals'] = [{symbol_map[k]: v for k, v in s.items()} for s in scaled_signals]
        activity_log['allocation'] = {symbol_map[k]: v for k, v in allocation.items()}
        activity_log['positions'] = {symbol_map[k]: v for k, v in positions.items()}

        # get relevant currencies and corresponding FX ratese
        currencies = {v['contract'].currency for v in contract_data.values()}
        fx = {
            c: 1 if c == base_currency else get_tickers(Forex(c + base_currency))
            for c in currencies
        }
        activity_log['fx'] = {
            v.contract.symbol + v.contract.currency: v.midpoint()
            if v.midpoint() == v.midpoint() else v.close
            for v in fx.values()
        }

        # calculate target positions
        target_positions = {
            k: round(config['exposure']['overall'] * v * net_liquidation
                     / (contract_data[k]['ticker'].close
                        * int(contract_data[k]['contract'].multiplier)
                        * (fx[contract_data[k]['contract'].currency].midpoint()
                           if fx[contract_data[k]['contract'].currency].midpoint() == fx[contract_data[k]['contract'].currency].midpoint()
                           else fx[contract_data[k]['contract'].currency].close)))
            for k, v in allocation.items()
        }

        for k in target_positions.keys():
            if k not in positions:
                positions[k] = 0
        for k in positions.keys():
            if k not in target_positions:
                target_positions[k] = 0
        activity_log['positions'] = {symbol_map[k]: v for k, v in positions.items()}
        activity_log['targetPositions'] = {symbol_map[k]: v for k, v in target_positions.items()}

        # calculate trade
        trades = {k: target_positions[k] - positions[k] for k in target_positions.keys()}
        trades = {k: int(v) for k, v in trades.items() if v != 0}
        activity_log['trades'] = {symbol_map[k]: v for k, v in trades.items()}
        logger.info('Trades: {}'.format(activity_log['trades']))

        perm_ids = []
        if not DRY_RUN:
            # place orders
            for k, v in trades.items():
                order = ib_gw.placeOrder(contract_data[k]['contract'],
                                         MarketOrder(action='BUY' if v > 0 else 'SELL',
                                                     totalQuantity=abs(v)).update(**order_properties))
                perm_ids.append(order.order.permId)
        ib_gw.sleep(5)  # give the IB Gateway a couple of seconds to digest orders and to raise possible errors
        activity_log['orders'] = {
            t.contract.localSymbol: {
                'order': {
                    k: v
                    for k, v in t.order.nonDefaults().items()
                    if isinstance(v, (int, float, str))
                },
                'orderStatus': {
                    k: v
                    for k, v in t.orderStatus.nonDefaults().items()
                    if isinstance(v, (int, float, str))
                },
                'isActive': t.isActive()
            } for t in ib_gw.trades() if t.order.permId in perm_ids
        }
        logging.info('Orders placed: {}'.format(activity_log['orders']))

    except Exception as e:
        logger.error(e)
        activity_log['exception'] = str(e)
        main_e = e

    finally:
        ib_gw.disconnect()

        try:
            activity_log['timestamp'] = datetime.now(timezone.utc)
            db.collection('activity').document().set(activity_log)
        except Exception as e:
            logger.error(e)
            logger.info(activity_log)

    if main_e is not None:
        # raise main exception so that CronJob is restarted
        raise main_e

    logger.info('Done.')


if __name__ == '__main__':
    main()
