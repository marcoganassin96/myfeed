#!/usr/bin/env python3
"""Set ECS service desired_count=0."""
import os
import subprocess
import sys


def main() -> None:
    cluster = os.environ["ECS_CLUSTER"]
    service = os.environ["ECS_SERVICE"]
    region  = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")

    subprocess.run(
        ["aws", "ecs", "update-service",
         "--cluster", cluster, "--service", service,
         "--desired-count", "0",
         "--region", region],
        check=True, capture_output=True,
    )
    print("Service scaled to 0.", file=sys.stderr)


if __name__ == "__main__":
    main()
