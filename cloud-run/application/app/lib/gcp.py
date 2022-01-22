import json
import logging
from os import environ

from google.cloud import bigquery, firestore_v1 as firestore, logging as gcp_logging, secretmanager_v1 as secretmanager

# set up Cloud Logging
on_localhost = environ.get('K_SERVICE', 'localhost') == 'localhost'
# logging.captureWarnings(True)
handler = logging.StreamHandler() if on_localhost else gcp_logging.Client().get_default_handler()
logger = logging.getLogger(__name__ if on_localhost else 'cloudLogger')
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False


class GcpModule:

    _bq = bigquery.Client()
    _db = firestore.Client()
    _logging = logger
    _sm = secretmanager.SecretManagerServiceClient()

    @property
    def bq(self):
        return self._bq

    @property
    def db(self):
        return self._db

    @property
    def logging(self):
        return self._logging

    @property
    def sm(self):
        return self._sm

    @classmethod
    def get_logger(cls):
        return cls._logging

    def get_secret(self, secret_name):
        """
        Fetches secrets from Secret Manager.

        :param secret_name: name of the secret
        :return: secret value (dict or str)
        """
        secret = self._sm.access_secret_version(name=secret_name).payload.data.decode()
        try:
            return json.loads(secret)
        except json.decoder.JSONDecodeError:
            return secret

    def query_bigquery(self, query, query_parameters=None, job_config=None, return_type='DataFrame', **kwargs):
        """
        Queries data form BigQuery.

        :param query: query string (str)
        :param query_parameters: parameters for parametrised query (dict)
        :param job_config: query job configuration (bigquery.job.QueryJobConfig)
        :param return_type: type of the return object (e.g. 'DataFrame') (str)
        :param kwargs: additional arguments for the fetch method
        :return: data (type depending on return_type, defaults to list of tuple)
        """
        query_parameters = query_parameters or {}
        job_config = job_config or bigquery.job.QueryJobConfig()

        def _create_query_parameters(params):
            parameter_types = {
                # dict: bigquery.StructQueryParameter,
                list: bigquery.ArrayQueryParameter
            }
            data_types = {
                bool: 'BOOL',
                int: 'INT64',
                float: 'FLOAT64',
                str: 'STRING'
            }

            query_parameters = []
            for k, v in params.items():
                ptype, dtype = type(v), type(v[0] if isinstance(v, list) else v)
                if dtype in data_types.keys():
                    query_parameters.append(
                        parameter_types.get(ptype, bigquery.ScalarQueryParameter)(k, data_types[dtype], v))
                else:
                    self._logging.warning(f'No BigQuery query parameter type for {v.__class__.__name__} available')

            return query_parameters

        try:
            job_config.query_parameters = _create_query_parameters(query_parameters)
        except Exception as e:
            self._logging.error(e)
            raise Exception('Query parameter error')

        try:
            self._logging.debug(f'Querying BigQuery with parameters {job_config.query_parameters}...')
            job = self._bq.query(query, job_config=job_config)
        except Exception as e:
            self._logging.error(f'BigQuery error: {e}')
            raise e

        try:
            if return_type.lower() == 'dataframe':
                to_dataframe_kwargs = {k: v for k, v in kwargs.items() if k in bigquery.QueryJob.to_dataframe.__code__.co_varnames}
                df = job.to_dataframe(**to_dataframe_kwargs)
                if 'index_col' in kwargs:
                    df.set_index(kwargs['index_col'], inplace=True)
                return df
            elif return_type.lower() == 'list':
                return [{k: v for k, v in row.items()} for row in job.result()]
            else:
                raise NotImplementedError(f'Return type "{return_type}" is not implemented')
        except NotImplementedError as e:
            raise e
        except Exception as e:
            self._logging.error(f'Error reading BigQuery result: {e}')
            raise e
