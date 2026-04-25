import pytest
from unittest.mock import MagicMock
from src.fields import LambdaEvent, HttpHeader


@pytest.fixture
def mock_db(mocker):
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("src.db.get_connection", return_value=mock_conn)
    return mock_cursor


@pytest.fixture
def mock_cache(mocker):
    mock_get = mocker.patch("src.cache.cache_get", return_value=None)
    mock_set = mocker.patch("src.cache.cache_set")
    return mock_get, mock_set


@pytest.fixture
def api_event():
    return {
        LambdaEvent.HTTP_METHOD: "GET",
        LambdaEvent.PATH: "/newsletters",
        LambdaEvent.RESOURCE: "/newsletters",
        LambdaEvent.PATH_PARAMETERS: None,
        LambdaEvent.QUERY_STRING_PARAMETERS: None,
        LambdaEvent.HEADERS: {HttpHeader.AUTHORIZATION: "Bearer test-token"},
        LambdaEvent.REQUEST_CONTEXT: {
            LambdaEvent.AUTHORIZER: {
                LambdaEvent.CLAIMS: {
                    LambdaEvent.SUB: "user-test-123",
                }
            }
        },
        LambdaEvent.BODY: None,
    }
