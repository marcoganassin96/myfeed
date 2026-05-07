#!/usr/bin/env python3
"""
Creates 100 Cognito test users and writes tokens to scripts/out/.

Outputs:
  scripts/out/{env}/00_tokens.txt  — one token per line (all 100)
  scripts/out/{env}/00_tokens.env  — export COGNITO_TOKEN=<first token>

Usage:
  CONFIG=config/dev.yaml python scripts/01_create_test_tokens.py

Env vars:
  CONFIG  path to YAML config file (default: config/local.yaml)
"""
import os
import pathlib
import sys

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import get_out_filepath, OutFile
from config import load as _cfg
from utils import timed

_cognito = _cfg()["cognito"]
REGION    = _cfg()["aws"]["region"]
POOL_ID   = _cognito["user_pool_id"]
CLIENT_ID = _cognito["client_id"]
PASSWORD  = "TestPass123!"
N_USERS   = 100

idp = boto3.client("cognito-idp", region_name=REGION)


def token_for(n: int) -> str:
    username = f"loadtest{n:03d}@example.com"
    try:
        idp.admin_create_user(UserPoolId=POOL_ID, Username=username,
                              TemporaryPassword=PASSWORD, MessageAction="SUPPRESS")
    except ClientError as e:
        if e.response["Error"]["Code"] != "UsernameExistsException":
            raise
    idp.admin_set_user_password(UserPoolId=POOL_ID, Username=username,
                                Password=PASSWORD, Permanent=True)
    resp = idp.initiate_auth(AuthFlow="USER_PASSWORD_AUTH",
                             AuthParameters={"USERNAME": username, "PASSWORD": PASSWORD},
                             ClientId=CLIENT_ID)
    return resp["AuthenticationResult"]["IdToken"]


if __name__ == "__main__":
    _env = os.environ.get("env", "local")
    with timed("Total time:"):
        tokens = []
        with timed("Created tokens"):
            for i in range(N_USERS):
                try:
                    tokens.append(token_for(i))
                    if i % 10 == 0:
                        print(f"  {i}/{N_USERS}", file=sys.stderr)
                except Exception as e:
                    print(f"  user {i} failed: {e}", file=sys.stderr)

        tokens_txt = get_out_filepath(_env, OutFile.TOKENS_TXT)
        tokens_env = get_out_filepath(_env, OutFile.TOKENS_ENV)
        tokens_txt.write_text("\n".join(tokens))
        tokens_env.write_text(f"export COGNITO_TOKEN={tokens[0]}\n")

        print(f"✓ {len(tokens)} tokens written to {tokens_txt}", file=sys.stderr)
        print("  next: python scripts/02_get_load_test_ids.py", file=sys.stderr)
