import functools
import os
import pathlib

import yaml

_ROOT = pathlib.Path(__file__).parent.parent.parent


def _merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result


@functools.lru_cache(maxsize=1)
def load() -> dict:
    env = os.environ.get("env", "local")
    common = _ROOT / "config" / "common.yaml"
    specific = _ROOT / "config" / f"{env}.yaml"
    with open(common) as f:
        data = yaml.safe_load(f) or {}
    with open(specific) as f:
        env_data = yaml.safe_load(f) or {}
    return _merge(data, env_data)
