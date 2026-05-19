#!/usr/bin/env python3
"""Set ECS service desired_count=2 and poll until 2 tasks are RUNNING (max 120s)."""
import json
import os
import subprocess
import sys
import time


def _aws(args: list[str]) -> dict:
    r = subprocess.run(
        ["aws"] + args + ["--output", "json"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)


def main() -> None:
    cluster = os.environ["ECS_CLUSTER"]
    service = os.environ["ECS_SERVICE"]
    region  = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
    base    = ["--region", region]

    subprocess.run(
        ["aws", "ecs", "update-service",
         "--cluster", cluster, "--service", service,
         "--desired-count", "2"] + base,
        check=True, capture_output=True,
    )
    print("Scaling to 2 tasks — waiting for RUNNING state...", file=sys.stderr)

    deadline = time.time() + 120
    while time.time() < deadline:
        data    = _aws(["ecs", "describe-services",
                        "--cluster", cluster, "--services", service] + base)
        running = data["services"][0]["runningCount"]
        print(f"  running: {running}/2", file=sys.stderr)
        if running >= 2:
            print("Tasks ready.", file=sys.stderr)
            return
        time.sleep(10)

    sys.exit("Timeout: fewer than 2 tasks RUNNING after 120s")


if __name__ == "__main__":
    main()
