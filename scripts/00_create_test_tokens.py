#!/usr/bin/env python3
"""
Creates 100 Cognito test users and writes tokens to scripts/out/.

Outputs:
  scripts/out/00_tokens.txt  — one token per line (all 100)
  scripts/out/00_tokens.env  — export COGNITO_TOKEN=<first token>

Usage:
  python scripts/00_create_test_tokens.py
  source scripts/out/00_tokens.env

Env vars: AWS_REGION, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID
"""
import os
import sys
import pathlib
import boto3
from botocore.exceptions import ClientError

REGION    = os.environ.get("AWS_REGION", "eu-west-1")
POOL_ID   = os.environ["COGNITO_USER_POOL_ID"]
CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]
PASSWORD  = "TestPass123!"
N_USERS   = 100
OUT_DIR   = pathlib.Path(__file__).parent / "out"
OUT_TOKENS_TXT = OUT_DIR / "00_tokens.txt"
OUT_TOKENS_ENV = OUT_DIR / "00_tokens.env"

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
    OUT_DIR.mkdir(exist_ok=True)
    tokens = []
    for i in range(N_USERS):
        try:
            tokens.append(token_for(i))
            if i % 10 == 0:
                print(f"  {i}/{N_USERS}", file=sys.stderr)
        except Exception as e:
            print(f"  user {i} failed: {e}", file=sys.stderr)

    OUT_TOKENS_TXT.write_text("\n".join(tokens))
    OUT_TOKENS_ENV.write_text(f"export COGNITO_TOKEN={tokens[0]}\n")

    print(f"✓ {len(tokens)} tokens written to {OUT_TOKENS_TXT}", file=sys.stderr)
    print("  next: python scripts/01_get_load_test_ids.py", file=sys.stderr)
