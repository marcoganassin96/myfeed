import os
import json
from unittest.mock import MagicMock
from src.fields import EnvVar


def test_get_client_creates_redis_client(mocker):
    mock_class = mocker.patch("redis.Redis")
    mock_client = MagicMock()
    mock_class.return_value = mock_client

    os.environ.update({EnvVar.REDIS_HOST: "localhost", EnvVar.REDIS_PORT: "6379"})

    import src.cache as cache_module
    cache_module._client = None

    client = cache_module.get_client()
    mock_class.assert_called_once_with(
        host="localhost", port=6379, ssl=False, decode_responses=True,
    )
    assert client is mock_client


def test_cache_get_returns_none_on_miss(mocker):
    mock_client = MagicMock()
    mock_client.get.return_value = None
    mocker.patch("src.cache.get_client", return_value=mock_client)

    from src.cache import cache_get
    assert cache_get("missing") is None
    mock_client.get.assert_called_once_with("missing")


def test_cache_get_parses_json_on_hit(mocker):
    payload = {"newsletter_id": "abc", "title": "Tech"}
    mock_client = MagicMock()
    mock_client.get.return_value = json.dumps(payload)
    mocker.patch("src.cache.get_client", return_value=mock_client)

    from src.cache import cache_get
    assert cache_get("newsletter:abc") == payload


def test_cache_set_serialises_with_ttl(mocker):
    mock_client = MagicMock()
    mocker.patch("src.cache.get_client", return_value=mock_client)

    from src.cache import cache_set
    data = {"title": "Tech"}
    cache_set("newsletter:abc", data, ttl=3600)
    mock_client.setex.assert_called_once_with(
        "newsletter:abc", 3600, json.dumps(data, default=str)
    )
