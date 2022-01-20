import unittest
from unittest.mock import call, MagicMock, patch

from strategies.dummy import Dummy
from strategies.dummy import randint


class TestVxcurve(unittest.TestCase):

    @patch('strategies.strategy.Environment')
    @patch.object(Dummy, '_get_signals')
    @patch.object(Dummy, '_setup')
    def setUp(self, *_):
        self.test_obj = Dummy()

    @patch('strategies.dummy.randint', return_value=12)
    @patch.object(Dummy, '_register_contracts')
    def test_get_signals(self, _register_contracts, randint):
        instruments = {
            'mnq': [MagicMock(contract=MagicMock(conId='mnq'))]
        }

        with patch.object(self.test_obj, '_instruments', instruments):
            expected = {
                instruments['mnq'][0].contract.conId: randint.return_value
            }
            self.test_obj._get_signals()
            self.assertDictEqual(expected, self.test_obj._signals)
            try:
                randint.assert_called_once_with(-1, 1)
                _register_contracts.assert_called_once_with(instruments['mnq'][0])
            except AssertionError:
                self.fail()

    @patch('strategies.dummy.Future.get_contract_series', return_value='contract-series')
    def test_setup(self, get_contract_series):
        expected = {
            'mnq': get_contract_series.return_value
        }
        self.test_obj._setup()
        self.assertDictEqual(expected, self.test_obj._instruments)
        try:
            get_contract_series.assert_called_once_with(1, 'MNQ', rollover_days_before_expiry=2)
        except AssertionError:
            self.fail()


if __name__ == '__main__':
    unittest.main()
