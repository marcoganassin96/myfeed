"""Central path constants for all scripts in this directory."""
import pathlib

SCRIPTS_DIR  = pathlib.Path(__file__).parent
ROOT_DIR     = SCRIPTS_DIR.parent
OUT_DIR      = SCRIPTS_DIR / "out"
CONFIG_DIR   = ROOT_DIR / "config"
CONFIG_LOCAL = CONFIG_DIR / "local.yaml"
CONFIG_DEV   = CONFIG_DIR / "dev.yaml"

# --- out/ files ---
TOKENS_TXT = OUT_DIR / "00_tokens.txt"
TOKENS_ENV = OUT_DIR / "00_tokens.env"
IDS_ENV    = OUT_DIR / "01_ids.env"

# --- script files (used by pipeline.py) ---
SEED_SCRIPT         = SCRIPTS_DIR / "00_seed.py"
TOKENS_SCRIPT       = SCRIPTS_DIR / "01_create_test_tokens.py"
IDS_SCRIPT          = SCRIPTS_DIR / "02_get_load_test_ids.py"
LOAD_TESTS_SCRIPT   = SCRIPTS_DIR / "03_run_load_tests.py"
