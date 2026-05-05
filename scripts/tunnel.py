#!/usr/bin/env python3
"""
Shared SSM port-forwarding context manager for scripts that need DB access.

Usage:
    from tunnel import ssm_tunnel

    with ssm_tunnel() as (host, port):
        conn = psycopg2.connect(host=host, port=port, ...)

Behaviour:
    - BASTION_ID set (env or Terraform output) → opens SSM tunnel to DB_HOST:5432
      on 127.0.0.1:15432, yields ("127.0.0.1", 15432), kills tunnel on exit.
    - No bastion found → yields (DB_HOST, DB_PORT) unchanged (localhost dev or
      already-tunnelled env from pipeline.py).
"""
import contextlib
import os
import pathlib
import signal
import socket
import subprocess
import sys
import time

LOCAL_PORT = 15433
TIMEOUT_S = 30


def _get_bastion_id() -> str | None:
    bid = os.environ.get("BASTION_ID", "").strip()
    if bid:
        return bid
    tf_dir = pathlib.Path(__file__).parent.parent / "terraform" / "envs" / "dev"
    if tf_dir.exists():
        result = subprocess.run(
            ["terraform", f"-chdir={tf_dir}", "output", "-raw", "bastion_instance_id"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


def _start(bastion_id: str, db_host: str) -> subprocess.Popen:
    region = os.environ.get("AWS_REGION", "eu-west-1")
    params = (
        f'{{"host":["{db_host}"],'
        f'"portNumber":["5432"],'
        f'"localPortNumber":["{LOCAL_PORT}"]}}'
    )
    proc = subprocess.Popen(
        [
            "aws", "ssm", "start-session",
            "--region", region,
            "--target", bastion_id,
            "--document-name", "AWS-StartPortForwardingSessionToRemoteHost",
            "--parameters", params,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"  SSM tunnel started (pid {proc.pid}) → localhost:{LOCAL_PORT}", file=sys.stderr)
    return proc


def _wait(proc: subprocess.Popen, timeout: int = TIMEOUT_S):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"SSM process exited early (code {proc.returncode}) — port {LOCAL_PORT} may already be in use")
        try:
            with socket.create_connection(("127.0.0.1", LOCAL_PORT), timeout=1):
                print("  Tunnel ready.", file=sys.stderr)
                return
        except OSError:
            time.sleep(1)
    raise TimeoutError(f"Tunnel not ready after {timeout}s")


def _kill(proc: subprocess.Popen):
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    print("  Tunnel closed.", file=sys.stderr)


@contextlib.contextmanager
def ssm_tunnel(db_host: str | None = None):
    db_host = db_host or os.environ["DB_HOST"]
    bastion_id = _get_bastion_id()

    if not bastion_id:
        yield db_host, int(os.environ.get("DB_PORT", "5432"))
        return

    print(f"  Bastion: {bastion_id}", file=sys.stderr)
    proc = _start(bastion_id, db_host)
    try:

        _wait(proc)
        yield "127.0.0.1", LOCAL_PORT
    finally:
        _kill(proc)
