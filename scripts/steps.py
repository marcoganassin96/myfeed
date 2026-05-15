from enum import StrEnum

LOAD_TEST_DIR = "load_tests"


class Step(StrEnum):
    # Lambda pipeline steps (unchanged)
    SEED     = "seed"
    TOKENS   = "tokens"
    IDS      = "ids"
    SMOKE    = "smoke"
    FLUSH    = "flush"
    UNCACHED = "uncached"
    PREWARM  = "prewarm"
    CACHED   = "cached"
    SSE      = "sse"
    MIXED    = "mixed"
    STRESS   = "stress"
    # Fargate-only steps
    SCALE_UP   = "scale_up"
    BENCHMARK  = "benchmark"
    SCALE_DOWN = "scale_down"


STEP_ORDER: list[Step] = [
    Step.SEED, Step.TOKENS, Step.IDS,
    Step.SMOKE, Step.FLUSH, Step.UNCACHED, Step.PREWARM,
    Step.CACHED, Step.SSE, Step.MIXED, Step.STRESS,
]

FARGATE_STEP_ORDER: list[Step] = [
    Step.SCALE_UP,
    Step.SEED, Step.TOKENS, Step.IDS,
    Step.SMOKE, Step.FLUSH, Step.UNCACHED, Step.PREWARM,
    Step.CACHED, Step.SSE, Step.MIXED, Step.BENCHMARK,
    Step.SCALE_DOWN,
]

K6_SCRIPTS: dict[Step, tuple[str, str]] = {
    Step.SMOKE:     ("smoke.js",               "1 VU · sanity check"),
    Step.UNCACHED:  ("newsletter_uncached.js",  "30s warmup → 200 VUs · p99<100ms"),
    Step.CACHED:    ("newsletter_cached.js",    "500 VUs · p99<50ms"),
    Step.SSE:       ("deep_dive_sse.js",        "50 VUs · p95<500ms"),
    Step.MIXED:     ("mixed_realistic.js",      "1000 VUs · p95<150ms"),
    Step.STRESS:    ("cold_start_stress.js",    "spike 0→1000 VUs · errors<1%"),
    Step.BENCHMARK: ("capacity_benchmark.js",   "stepped ramp · observation only"),
}

DB_STEPS: set[Step] = {Step.SEED, Step.IDS}
