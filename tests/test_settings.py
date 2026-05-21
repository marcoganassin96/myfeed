import sys
import pytest


def test_load_merges_common_and_env(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "common.yaml").write_text(
        "mdg:\n  connect_timeout: 2.0\n  read_timeout: 10.0\ncache:\n  ttl: 3600\n"
    )
    (tmp_path / "config" / "test.yaml").write_text(
        "mdg:\n  url: http://mdg:9000\n"
    )
    monkeypatch.setenv("env", "test")

    sys.modules.pop("settings", None)
    import settings
    settings._ROOT = tmp_path
    settings.load.cache_clear()

    cfg = settings.load()
    assert cfg["mdg"]["url"] == "http://mdg:9000"
    assert cfg["mdg"]["connect_timeout"] == 2.0
    assert cfg["cache"]["ttl"] == 3600

    settings.load.cache_clear()
