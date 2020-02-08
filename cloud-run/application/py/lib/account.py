from ib_insync import util


ACCOUNT_VALUE_TIMEOUT = 60


def get_account_values(ib_gw, account):
    """
    Requests account data from IB.

    :param ib_gw: IB API (IBGW or ib_insync IB object)
    :param account: account identifier (str)
    :return: account data (dict)
    """

    account_summary = {}
    av = []
    timeout = ACCOUNT_VALUE_TIMEOUT
    while not len(av) and timeout:
        # needs several attempts sometimes, so let's retry
        ib_gw.sleep(1)
        av = ib_gw.accountValues(account)
        timeout -= 1
    if len(av):
        # TODO: make rows a function argument
        rows = ['NetLiquidation', 'CashBalance', 'MaintMarginReq']
        # filter rows and build dict
        account_values = util.df(av).set_index(['tag', 'currency']).loc[rows, 'value']
        for (k, c), v in account_values.items():
            if c != 'BASE':
                if k in account_summary:
                    account_summary[k][c] = float(v)
                else:
                    account_summary[k] = {c: float(v)}

    return account_summary
