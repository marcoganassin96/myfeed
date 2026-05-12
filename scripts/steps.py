from enum import StrEnum

LOAD_TEST_DIR = "load_tests"


class Step(StrEnum):
    SEED    = "seed"
    TOKENS  = "tokens"
    IDS     = "ids"
    SMOKE   = "smoke"
    COLD    = "cold"
    PREWARM = "prewarm"
    CACHED  = "cached"
    SSE     = "sse"
    MIXED   = "mixed"
    STRESS  = "stress"


STEP_ORDER: list[Step] = [
    Step.SEED, Step.TOKENS, Step.IDS,
    Step.SMOKE, Step.COLD, Step.PREWARM,
    Step.CACHED, Step.SSE, Step.MIXED, Step.STRESS,
]

K6_SCRIPTS: dict[Step, tuple[str, str]] = {
    Step.SMOKE:  ("smoke.js",             "1 VU · sanity check"),
    Step.COLD:   ("newsletter_cold.js",   "200 VUs · p99<300ms"),
    Step.CACHED: ("newsletter_cached.js", "500 VUs · p99<50ms"),
    Step.SSE:    ("deep_dive_sse.js",     "50 VUs · first chunk<500ms"),
    Step.MIXED:  ("mixed_realistic.js",   "1000 VUs · p95<200ms"),
    Step.STRESS: ("cold_start_stress.js", "spike 0→1000 VUs · errors<1%"),
}

DB_STEPS: set[Step] = {Step.SEED, Step.IDS}
