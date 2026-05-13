import sys
from contextlib import contextmanager
from datetime import datetime


@contextmanager
def timed(label: str):
    t0 = datetime.now()
    try:
        yield
    finally:
        print(f"✓ {label} {(datetime.now() - t0).total_seconds():.2f}s")


def die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)
