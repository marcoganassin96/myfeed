#!/usr/bin/env python3
"""
Shared SSM port-forwarding context manager for scripts that need DB/Redis access.

Usage:
    from tunnel import ssm_tunnel, Service

    with ssm_tunnel(Service.DB) as (host, port):
        conn = psycopg2.connect(host=host, port=port, ...)

    with ssm_tunnel(Service.REDIS) as (host, port):
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
from dataclasses import dataclass
from enum import StrEnum

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import load as _cfg

TIMEOUT_S = 30


@dataclass
class ServiceConfig:
    name: str
    host: str
    remote_port: int
    local_port: int


class Service(StrEnum):
    DB = "database"
    REDIS = "redis"

    def config(self, host_override: str | None = None) -> ServiceConfig:
        section = _cfg()[str(self)]
        env_prefix = {"database": "DB", "redis": "REDIS"}[str(self)]
        host = host_override or os.environ.get(f"{env_prefix}_HOST") or section["host"]
        remote_port = int(os.environ.get(f"{env_prefix}_PORT") or section["port"])
        return ServiceConfig(
            name=str(self),
            host=host,
            remote_port=remote_port,
            local_port=section["local_port"],
        )


def _aws_region() -> str:
    return os.environ.get("AWS_REGION") or _cfg()["aws"]["region"]


def _get_bastion_id() -> str | None:
    bid = os.environ.get("BASTION_ID", "").strip()
    if bid:
        return bid
    tf_dir = pathlib.Path(__file__).parent.parent.parent / "terraform" / "envs" / "dev"
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
            raise RuntimeError(
                f"SSM process exited early (code {proc.returncode}) "
                f"— port {local_port} may already be in use"
            )
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
def ssm_tunnel(service: Service, host: str | None = None):
    cfg = service.config(host_override=host)
    bastion_id = _get_bastion_id()

    if not bastion_id:
        yield cfg.host, cfg.remote_port
        return

    print(f"  Bastion: {bastion_id}", file=sys.stderr)
    proc = _start(bastion_id, cfg.host, cfg.remote_port, cfg.local_port)
    try:
        _wait(proc, cfg.local_port)
        yield "127.0.0.1", cfg.local_port
    finally:
        _kill(proc)
