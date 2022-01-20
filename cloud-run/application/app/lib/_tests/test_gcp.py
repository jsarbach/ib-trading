from google.cloud.bigquery import ArrayQueryParameter, ScalarQueryParameter
from pandas import DataFrame
import unittest
from unittest.mock import MagicMock, patch

with patch('lib.gcp.bigquery'):
    with patch('lib.gcp.firestore'):
        with patch('lib.gcp.secretmanager'):
            from lib.gcp import GcpModule


class TestGcpModule(unittest.TestCase):

    def setUp(self, *_):
        self.test_obj = GcpModule()

    def test_get_secret(self):
        with patch.object(self.test_obj, '_sm', access_secret_version=MagicMock(return_value=MagicMock(payload=MagicMock(data=MagicMock(decode=MagicMock(return_value='{"key":"secret-value"}')))))) as p:
            actual = self.test_obj.get_secret('secret-name')
            self.assertDictEqual({'key': 'secret-value'}, actual)
            try:
                p.access_secret_version.assert_called_once_with(name='secret-name')
            except AssertionError:
                self.fail()

        with patch.object(self.test_obj, '_sm', access_secret_version=MagicMock(return_value=MagicMock(payload=MagicMock(data=MagicMock(decode=MagicMock(return_value='secret-value')))))) as p:
            actual = self.test_obj.get_secret('secret-name')
            self.assertEqual('secret-value', actual)

    @patch('lib.gcp.bigquery.job.QueryJobConfig', config='something', query_parameters=[])
    def test_query_bigquery(self, query_job_config):
        func = self.test_obj.query_bigquery
        data = [[1, 2, 3], [4, 5, 6]]

        with patch.object(GcpModule._bq, 'query',
                          MagicMock(return_value=MagicMock(result=MagicMock(return_value=[MagicMock(items=MagicMock(return_value=[(f'col{i + 1}', v) for i, v in enumerate(row)])) for row in data]),
                                                           to_dataframe=MagicMock(return_value=DataFrame({f'col{i + 1}': v for i, v in enumerate(list(map(list, zip(*data))))}))))) as p:
            actual = func('query_str', job_config=query_job_config, return_type='list')
            expected = [{'col1': 1, 'col2': 2, 'col3': 3}, {'col1': 4, 'col2': 5, 'col3': 6}]
            self.assertEqual(expected, actual)
            try:
                p.assert_called_with('query_str', job_config=query_job_config)
            except AssertionError as e:
                self.fail(e)

            func('query_str', query_parameters={'str': 'str', 'int': 1, 'list': ['str1', 'str2'], 'none': None}, job_config=query_job_config, return_type='list')
            expected = [ScalarQueryParameter('str', 'STRING', 'str'), ScalarQueryParameter('int', 'INT64', 1), ArrayQueryParameter('list', 'STRING', ['str1', 'str2'])]
            self.assertListEqual(expected, query_job_config.query_parameters)
            try:
                p.assert_called_with('query_str', job_config=query_job_config)
            except AssertionError as e:
                self.fail(e)

            func('query_str', job_config=query_job_config, return_type='list')
            try:
                p.assert_called_with('query_str', job_config=query_job_config)
            except AssertionError as e:
                self.fail(e)

            df = DataFrame({'col1': [1, 4], 'col2': [2, 5], 'col3': [3, 6]})
            expected = df
            actual = func('query_str', job_config=query_job_config, return_type='DataFrame')
            self.assertTrue(actual.equals(expected))
            try:
                p.return_value.to_dataframe.assert_called_once()
            except AssertionError as e:
                self.fail(e)

            expected = df.set_index('col1')
            actual = func('query_str', job_config=query_job_config, return_type='DataFrame', index_col='col1')
            self.assertTrue(actual.equals(expected))

            self.assertRaises(NotImplementedError, func, 'query_str', {}, query_job_config, 'NotImplemented')

            p.return_value.to_dataframe.side_effect = Exception
            self.assertRaises(Exception, func)

            p.return_value.side_effect = Exception
            self.assertRaises(Exception, func)


if __name__ == '__main__':
    unittest.main()
