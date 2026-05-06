#!/usr/bin/env python3
"""
Shared SSM port-forwarding context managers for scripts that need DB/Redis access.

Usage:
    from tunnel import ssm_tunnel, ssm_redis_tunnel

    with ssm_tunnel() as (host, port):
        conn = psycopg2.connect(host=host, port=port, ...)

    with ssm_redis_tunnel() as (host, port):
        rc = redis.Redis(host=host, port=port, ssl=True, ssl_cert_reqs=None, ...)

Behaviour:
    - BASTION_ID set (env or Terraform output) → opens SSM tunnel to remote host:port
      on 127.0.0.1:<local_port>, yields ("127.0.0.1", local_port), kills tunnel on exit.
    - No bastion found → yields (remote_host, remote_port) unchanged.
"""
import contextlib
import os
import pathlib
import signal
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import load as _cfg

LOCAL_DB_PORT = 15433
LOCAL_REDIS_PORT = 16379
TIMEOUT_S = 30


def _db_host() -> str:
    return os.environ.get("DB_HOST") or _cfg()["database"]["host"]


def _db_port() -> int:
    return int(os.environ.get("DB_PORT") or _cfg()["database"]["port"])


def _redis_host() -> str:
    return os.environ.get("REDIS_HOST") or _cfg()["redis"]["host"]


def _redis_port() -> int:
    return int(os.environ.get("REDIS_PORT") or _cfg()["redis"]["port"])


def _aws_region() -> str:
    return os.environ.get("AWS_REGION") or _cfg()["aws"]["region"]


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


def _start(bastion_id: str, remote_host: str, remote_port: int, local_port: int) -> subprocess.Popen:
    params = (
        f'{{"host":["{remote_host}"],'
        f'"portNumber":["{remote_port}"],'
        f'"localPortNumber":["{local_port}"]}}'
    )
    proc = subprocess.Popen(
        [
            "aws", "ssm", "start-session",
            "--region", _aws_region(),
            "--target", bastion_id,
            "--document-name", "AWS-StartPortForwardingSessionToRemoteHost",
            "--parameters", params,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"  SSM tunnel started (pid {proc.pid}) → localhost:{local_port}", file=sys.stderr)
    return proc


def _wait(proc: subprocess.Popen, local_port: int, timeout: int = TIMEOUT_S):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"SSM process exited early (code {proc.returncode}) — port {local_port} may already be in use")
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=1):
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
    db_host = db_host or _db_host()
    bastion_id = _get_bastion_id()

    if not bastion_id:
        yield db_host, _db_port()
        return

    print(f"  Bastion: {bastion_id}", file=sys.stderr)
    proc = _start(bastion_id, db_host, 5432, LOCAL_DB_PORT)
    try:
        _wait(proc, LOCAL_DB_PORT)
        yield "127.0.0.1", LOCAL_DB_PORT
    finally:
        _kill(proc)


@contextlib.contextmanager
def ssm_redis_tunnel(redis_host: str | None = None):
    redis_host = redis_host or _redis_host()
    bastion_id = _get_bastion_id()

    if not bastion_id:
        yield redis_host, _redis_port()
        return

    print(f"  Bastion: {bastion_id}", file=sys.stderr)
    proc = _start(bastion_id, redis_host, 6379, LOCAL_REDIS_PORT)
    try:
        _wait(proc, LOCAL_REDIS_PORT)
        yield "127.0.0.1", LOCAL_REDIS_PORT
    finally:
        _kill(proc)
