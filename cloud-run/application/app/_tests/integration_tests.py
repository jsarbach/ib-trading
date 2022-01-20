from datetime import date
from google.cloud.bigquery.job import LoadJobConfig, WriteDisposition
from google.cloud.firestore_v1 import DELETE_FIELD
from os import environ, listdir
from pandas import DataFrame
import re
from time import sleep
import unittest
from unittest.mock import patch
from uuid import uuid1

if environ.get('K_REVISION') != 'localhost':
    from lib.environment import Environment
    env = {
        key: environ.get(key) for key in
        ['ibcIni', 'ibcPath', 'javaPath', 'twsPath', 'twsSettingsPath']
    }
    env['javaPath'] += '/{}/bin'.format(listdir(env['javaPath'])[0])
    with open(environ.get('TWS_INSTALL_LOG'), 'r') as fp:
        install_log = fp.read()
    ibc_config = {
        'gateway': True,
        'twsVersion': re.search('IB Gateway ([0-9]{3})', install_log).group(1),
        **env
    }
    Environment('paper', ibc_config)

from intents.intent import Intent
from lib.gcp import GcpModule


class TestGcpModule(unittest.TestCase):

    BIGQUERY_DESTINATION = 'historical_data.test'
    BIGQUERY_JOB_CONFIG = LoadJobConfig(write_disposition=WriteDisposition.WRITE_APPEND)
    FIRESTORE_COLLECTION = 'tests'

    def setUp(self):
        self.gcp_module = GcpModule()

    def test_bigquery(self):
        dt = date(1977, 9, 27)
        key = str(uuid1())
        query = f"SELECT date, value FROM `{self.BIGQUERY_DESTINATION}` WHERE instrument='test' AND key='{key}'"

        data = DataFrame({'date': [dt], 'instrument': ['test'], 'key': [key], 'value': [42.0]})
        load_job = self.gcp_module.bq.load_table_from_dataframe(data, self.BIGQUERY_DESTINATION, job_config=self.BIGQUERY_JOB_CONFIG)
        self.assertTrue(load_job.done)
        sleep(5)  # give it time to materialise

        result = self.gcp_module.bq.query(query).result()
        rows = [{k: v for k, v in row.items()} for row in result]
        self.assertEqual(1, len(rows))
        self.assertDictEqual({'date': dt, 'value': 42.0}, rows[0])

        df = self.gcp_module.bq.query(query).to_dataframe()
        self.assertTrue(data.loc[:, ['date', 'value']].equals(df))

    def test_firestore(self):
        col_ref = self.gcp_module.db.collection(self.FIRESTORE_COLLECTION)
        doc_ref = col_ref.document()
        doc_ref.set({'key': 'value'})
        doc_ref.update({'anotherKey': 'anotherValue'})

        actual = doc_ref.get().to_dict()
        self.assertDictEqual({'key': 'value', 'anotherKey': 'anotherValue'}, actual)

        result = [*col_ref.where('key', '==', 'value').get()]
        self.assertEqual(1, len(result))
        self.assertEqual(doc_ref.id, result[0].id)

        doc_ref.update({'anotherKey': DELETE_FIELD})
        actual = doc_ref.get().to_dict()
        self.assertDictEqual({'key': 'value'}, actual)

        doc_ref.delete()
        result = [*col_ref.where('key', '==', 'value').get()]
        self.assertEqual(0, len(result))

    def test_logging(self):
        try:
            self.gcp_module.logging.debug('Test log entry from integration test')
        except Exception as e:
            self.fail(e)


class TestIbgw(unittest.TestCase):

    @patch('intents.intent.Intent._log_activity')
    def test_intent(self, *_):
        intent = Intent()
        if environ.get('K_REVISION') == 'localhost':
            try:
                intent._env.ibgw.connect(port=4001)
                actual = intent._core()
            except Exception as e:
                self.fail(e)
            finally:
                intent._env.ibgw.disconnect()
        else:
            actual = intent.run()

        self.assertEqual(date.today().isoformat(), actual.get('currentTime', '')[:10])


if __name__ == '__main__':
    unittest.main()
