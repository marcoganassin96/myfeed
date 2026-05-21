"""YAML config loader. CONFIG env var selects the file; defaults to config/local.yaml."""
import functools
import os
import pathlib

import yaml

_ROOT = pathlib.Path(__file__).parent.parent.parent
_DEFAULT = _ROOT / "config" / "local.yaml"
CONFIG_PATH = _ROOT / "config"


@functools.lru_cache(maxsize=1)
def load() -> dict:
    if "env" not in os.environ:
        print(f"CONFIG env var not set, defaulting to {_DEFAULT}")
    env = os.environ.get("env", "local")
    path = CONFIG_PATH / f"{env}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)
