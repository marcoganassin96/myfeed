#!/usr/bin/env python3
"""
Creates 100 Cognito test users and prints Bearer tokens to stdout.
Run once after SAM deploy.
Usage: python scripts/create_test_tokens.py
Env vars: AWS_REGION, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID
"""
import os, sys, boto3
from botocore.exceptions import ClientError

REGION    = os.environ.get("AWS_REGION", "eu-west-1")
POOL_ID   = os.environ["COGNITO_USER_POOL_ID"]
CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]
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
    tokens = []
    for i in range(N_USERS):
        try:
            tokens.append(token_for(i))
            if i % 10 == 0:
                print(f"  {i}/{N_USERS}", file=sys.stderr)
        except Exception as e:
            print(f"  user {i} failed: {e}", file=sys.stderr)

    print("\n".join(tokens))
    print(f"\n✓ {len(tokens)} tokens. Use first as COGNITO_TOKEN:", file=sys.stderr)
    print(f"  export COGNITO_TOKEN=$(python scripts/create_test_tokens.py | head -1)", file=sys.stderr)
