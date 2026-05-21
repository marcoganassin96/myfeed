"""Central path constants for all scripts in this directory."""
import pathlib
from enum import StrEnum

SCRIPTS_DIR  = pathlib.Path(__file__).parent
ROOT_DIR     = SCRIPTS_DIR.parent.parent
OUT_DIR      = SCRIPTS_DIR / "out"
CONFIG_DIR   = ROOT_DIR / "config"
CONFIG_LOCAL = CONFIG_DIR / "local.yaml"
CONFIG_DEV   = CONFIG_DIR / "dev.yaml"

class OutFile(StrEnum):
    SEED_RESULT = "00_seed_result.json"
    TOKENS_TXT  = "02_tokens.txt"
    TOKENS_ENV  = "02_tokens.env"
    IDS_ENV     = "03_ids.env"

def get_out_filepath(env: str, file_name: OutFile) -> pathlib.Path:
    path = OUT_DIR / env / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

# --- script files (used by pipeline.py) ---
SEED_SCRIPT         = SCRIPTS_DIR / "00_seed.py"
PREWARM_SCRIPT      = SCRIPTS_DIR / "01_prewarm.py"
TOKENS_SCRIPT       = SCRIPTS_DIR / "02_create_test_tokens.py"
IDS_SCRIPT          = SCRIPTS_DIR / "03_get_load_test_ids.py"
LOAD_TESTS_SCRIPT   = SCRIPTS_DIR / "04_run_load_tests.py"
FLUSH_SCRIPT        = SCRIPTS_DIR / "flush_redis.py"
SCALE_UP_SCRIPT       = SCRIPTS_DIR / "scale_up.py"
SCALE_DOWN_SCRIPT     = SCRIPTS_DIR / "scale_down.py"
