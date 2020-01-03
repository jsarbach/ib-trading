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

# instantiate Firestore Client and query config
db = firestore.Client()
config = db.collection('config').document('paper' if TRADING_MODE == 'local' else TRADING_MODE).get().to_dict()

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


def get_contract_details(contract_ids=()):
    """
    Requests contract details and price (tick) data

    :param contract_ids: iterable of IB contract IDs
    :return: contract details (dict)
    """
    contract_data = {}
    for con_id in contract_ids:
        contract_data[con_id] = {}
        contract = ib_gw.reqContractDetails(Contract(conId=con_id))[0].contract
        contract_data[con_id]['contract'] = contract
        logger.info('Requesting tick data for {}...'.format(contract.localSymbol))
        contract_data[con_id]['tickData'] = ib_gw.reqTickers(contract)[0]

    return contract_data


def get_positions(account):
    """
    Requests current portfolio positions

    :param account: IB account number
    :return: positions per contract ID (dict)
    """
    positions = {}
    for item in ib_gw.positions(account):
        positions[str(item.contract.conId)] = item.position

    return positions


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
        positions = get_positions(config['account'])
        activity_log['positions'] = positions

        # get contract details
        contract_details = get_contract_details(set(list(allocation.keys()) + list(positions.keys())))
        # build contractId<->symbol lookup dict
        symbol_map = {
            'conid_symbol': {k: v['contract'].localSymbol for k, v in contract_details.items()},
            'symbol_conid': {v['contract'].localSymbol: k for k, v in contract_details.items()}
        }
        activity_log['contractIds'] = symbol_map['symbol_conid']
        # replace dict items
        activity_log['signals'] = {k: {symbol_map['conid_symbol'][k]: v for k, v in v.items()} for k, v in signals.items()}
        activity_log['scaledSignals'] = [{symbol_map['conid_symbol'][k]: v for k, v in s.items()} for s in scaled_signals]
        activity_log['allocation'] = {symbol_map['conid_symbol'][k]: v for k, v in allocation.items()}
        activity_log['positions'] = {symbol_map['conid_symbol'][k]: v for k, v in positions.items()}

        # get relevant currencies and corresponding FX ratese
        currencies = {v['contract'].currency for v in contract_details.values()}
        fx = {}
        for c in currencies:
            fx[c] = 1 if c == base_currency else ib_gw.reqTickers(Forex(c + base_currency))[0]
        activity_log['fx'] = {
            v.contract.symbol + v.contract.currency: v.midpoint()
            if v.midpoint() == v.midpoint() else v.close
            for v in fx.values()
        }

        # calculate target positions
        target_positions = {
            k: round(config['exposure']['overall'] * v * net_liquidation
                     / (contract_details[k]['tickData'].close
                        * int(contract_details[k]['contract'].multiplier)
                        * (fx[contract_details[k]['contract'].currency].midpoint()
                           if fx[contract_details[k]['contract'].currency].midpoint() == fx[contract_details[k]['contract'].currency].midpoint()
                           else fx[contract_details[k]['contract'].currency].close)))
            for k, v in allocation.items()
        }

        for k in target_positions.keys():
            if k not in positions:
                positions[k] = 0
        for k in positions.keys():
            if k not in target_positions:
                target_positions[k] = 0
        activity_log['positions'] = {symbol_map['conid_symbol'][k]: v for k, v in positions.items()}
        activity_log['targetPositions'] = {symbol_map['conid_symbol'][k]: v for k, v in target_positions.items()}

        # calculate trade
        trades = {}
        for k in target_positions.keys():
            trades[k] = target_positions[k] - positions[k]
        trades = {k: int(v) for k, v in trades.items() if v != 0}
        activity_log['trades'] = {symbol_map['conid_symbol'][k]: v for k, v in trades.items()}
        logger.info('Trades: {}'.format(activity_log['trades']))

        if not DRY_RUN:
            # parse order properties
            order_properties = {k: v for k, v in order_properties.items() if k in MarketOrder.defaults.keys()}

            # place orders
            for k, v in trades.items():
                ib_gw.placeOrder(ib_gw.reqContractDetails(Contract(conId=k))[0].contract,
                                 MarketOrder('BUY' if v > 0 else 'SELL', abs(v), **order_properties))
        activity_log['orders'] = {
            t.contract.localSymbol: {
                'order': {
                    k: v
                    for k, v in t.order.dict().items()
                    if v is not '' and (isinstance(v, str) or isinstance(v, (int, float)) and v < 2147483647)
                },
                'orderStatus': {
                    k: v
                    for k, v in t.orderStatus.dict().items()
                    if v is not '' and isinstance(v, (int, float, str))
                },
                'isActive': t.isActive()
            } for t in ib_gw.trades()
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
