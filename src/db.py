import os
import psycopg2
import psycopg2.extras
from fields import EnvVar

_connection = None


def get_connection():
    global _connection
    if _connection is None or _connection.closed:
        _connection = psycopg2.connect(
            host=os.environ[EnvVar.DB_HOST],
            port=int(os.environ.get(EnvVar.DB_PORT, "5432")),
            dbname=os.environ[EnvVar.DB_NAME],
            user=os.environ[EnvVar.DB_USER],
            password=os.environ[EnvVar.DB_PASSWORD],
            connect_timeout=5,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _connection
