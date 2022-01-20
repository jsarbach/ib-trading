from unittest.mock import patch

with patch('google.cloud.bigquery.Client'):
    with patch('google.cloud.firestore_v1.Client'):
        with patch('google.cloud.logging.Client'):
            with patch('google.cloud.secretmanager_v1.SecretManagerServiceClient'):
                from lib.environment import Environment

with patch('lib.environment.environ', {'PROJECT_ID': 'project-id'}):
    with patch('lib.environment.GcpModule.get_secret', return_value={'userid': 'userid', 'password': 'password'}):
        env = Environment()
