import os
import pytest
from unittest.mock import MagicMock
import psycopg2.extras
from fields import EnvVar


def test_get_connection_creates_connection_with_env_vars(mocker):
    mock_connect = mocker.patch("psycopg2.connect")
    mock_conn = MagicMock()
    mock_conn.closed = 0
    mock_connect.return_value = mock_conn

    os.environ.update({
        EnvVar.DB_HOST: "localhost", EnvVar.DB_PORT: "5432",
        EnvVar.DB_NAME: "newsletter", EnvVar.DB_USER: "newsletter", EnvVar.DB_PASSWORD: "newsletter",
    })

    import db as db_module
    db_module._connection = None

    conn = db_module.get_connection()

    mock_connect.assert_called_once_with(
        host="localhost", port=5432, dbname="newsletter",
        user="newsletter", password="newsletter",
        connect_timeout=5, cursor_factory=mocker.ANY,
    )
    assert conn is mock_conn


def test_get_connection_reuses_open_connection(mocker):
    mock_connect = mocker.patch("psycopg2.connect")
    existing = MagicMock()
    existing.closed = 0

    import db as db_module
    db_module._connection = existing

    assert db_module.get_connection() is existing
    mock_connect.assert_not_called()


def test_get_connection_reconnects_when_closed(mocker):
    new_conn = MagicMock()
    new_conn.closed = 0
    mocker.patch("psycopg2.connect", return_value=new_conn)

    closed = MagicMock()
    closed.closed = 1

    import db as db_module
    db_module._connection = closed

    assert db_module.get_connection() is new_conn
