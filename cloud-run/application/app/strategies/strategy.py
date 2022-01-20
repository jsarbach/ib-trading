from lib.environment import Environment
from lib.trading import Contract, Forex, Instrument, InstrumentSet


class Strategy:

    _contracts = {}
    _fx = {}
    _holdings = {}
    _instruments = {}
    _signals = {}
    _target_positions = {}
    _trades = {}

    def __init__(self, _id=None, **kwargs):
        self._id = _id or self.__class__.__name__.lower()
        self._env = Environment()
        self._base_currency = kwargs.get('base_currency', None)
        self._exposure = kwargs.get('exposure', 0)

        self._setup()

        self._get_signals()
        self._get_holdings()

        # complete holdings and signals w/ missing contracts from union
        contract_ids = set([*self._signals.keys()] + [*self._holdings.keys()])
        self._holdings = {
            **{cid: 0 for cid in contract_ids},
            **self._holdings
        }
        self._signals = {
            **{cid: 0 for cid in contract_ids},
            **self._signals
        }
        assert all(k in self._holdings.keys() for k in contract_ids)

        self._calculate_target_positions()
        self._calculate_trades()

    @property
    def contracts(self):
        return self._contracts

    @property
    def fx(self):
        return self._fx

    @property
    def holdings(self):
        return self._holdings

    @property
    def id(self):
        return self._id

    @property
    def signals(self):
        return self._signals

    @property
    def target_positions(self):
        return self._target_positions

    @property
    def trades(self):
        return self._trades

    def _calculate_target_positions(self):
        """
        Converts signals into target positions (number of contracts).
        """
        if self._base_currency is not None and self._exposure:
            for k in self._signals.keys():
                # make sure we have tickers for all contracts needed
                if (c := self._contracts[k]).tickers is None:
                    c.get_tickers()
            self._get_currencies(self._base_currency)

            self._target_positions = {
                k: round(self._exposure * v
                         / (self._contracts[k].tickers.close
                            * int(self._contracts[k].contract.multiplier)
                            * self._fx[self._contracts[k].contract.currency])) if v else 0
                for k, v in self._signals.items()
            }
        else:
            # TODO: review
            self._target_positions = {k: 0 for k in self._signals.keys()}

    def _calculate_trades(self):
        """
        Converts target positions into trades (subtract current holdings)
        """
        self._trades = {
            k: v - self._holdings[k]
            for k, v in self._target_positions.items()
            if v - self._holdings[k]
        }
        self._env.logging.info(f"Trades for {self._id}: { {self._contracts[k].local_symbol: v for k, v in self._trades.items()} }")

    def _get_currencies(self, base_currency):
        """
        Gets the FX rates for all involved contracts.

        :param base_currency: base currency of IB account in ISO format (str)
        """
        currencies = {c.contract.currency for c in self._contracts.values()}
        forex = InstrumentSet(*[Forex(pair=c + base_currency) for c in currencies])
        forex.get_tickers()
        fx_rates = [f.tickers.midpoint() if f.tickers.midpoint() == f.tickers.midpoint() else f.tickers.close
                    for f in forex]
        self._fx = {
            currency: 1 if currency == base_currency else fx_rate
            for currency, fx_rate in zip(currencies, fx_rates)
        }

    def _get_holdings(self):
        """
        Gets current portfolio holdings from Firestore.
        """
        doc = self._env.db.document(f'positions/{self._env.trading_mode}/holdings/{self._id}').get()
        self._holdings = {
            int(k): v
            for k, v in doc.to_dict().items()
        } if doc.exists else {}
        self._register_contracts(*self._holdings.keys())

    def _get_signals(self):
        self._signals = {
            k: 0 for k in self._holdings.keys()
        }

    def _register_contracts(self, *contracts):
        if not all(isinstance(c, (int, Instrument)) for c in contracts):
            raise TypeError('Not all contracts are of type int or Instrument')

        # add to _contracts if not in it yet
        to_add = {
            k: v
            for k, v in {
                c if isinstance(c, int) else c.contract.conId: Contract(conId=c) if isinstance(c, int) else c
                for c in contracts
            }.items()
            if k not in self._contracts.keys()
        }
        self._contracts = {**self._contracts, **to_add}

    def _setup(self):
        pass
