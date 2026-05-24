"""
Infrastructure — IAM Roles & Policies for AgentCore Patterns
=============================================================
Creates all IAM roles required to run the patterns in this repo:
  • BedrockAgentCoreExecutionRole  — used by AgentCore Runtime containers
  • BedrockAgentCoreGatewayRole    — used by AgentCore Gateway to call targets
  • BedrockAgentCoreLambdaRole     — used by Lambda functions registered as Gateway targets

Usage:
    python infra/iam_setup.py
"""

import os
import json
import logging
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID")

iam = boto3.client("iam")

# ── Trust policies ─────────────────────────────────────────────────────────────

AGENTCORE_RUNTIME_TRUST = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}

LAMBDA_TRUST = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}

# ── Inline policies ────────────────────────────────────────────────────────────

EXECUTION_ROLE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BedrockInvoke",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
            ],
            "Resource": "*",
        },
        {
            "Sid": "ECRAccess",
            "Effect": "Allow",
            "Action": [
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "ecr:GetAuthorizationToken",
            ],
            "Resource": "*",
        },
        {
            "Sid": "CloudWatchLogs",
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
            "Resource": "arn:aws:logs:*:*:*",
        },
        {
            "Sid": "AgentCoreMemory",
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:CreateEvent",
                "bedrock-agentcore:ListEvents",
                "bedrock-agentcore:RetrieveMemoryRecords",
                "bedrock-agentcore:ListMemoryRecords",
            ],
            "Resource": "*",
        },
    ],
}

GATEWAY_ROLE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "InvokeLambda",
            "Effect": "Allow",
            "Action": "lambda:InvokeFunction",
            "Resource": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:AgentCoreGateway*",
        },
        {
            "Sid": "CloudWatchLogs",
            "Effect": "Allow",
            "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            "Resource": "arn:aws:logs:*:*:*",
        },
    ],
}

LAMBDA_ROLE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BasicExecution",
            "Effect": "Allow",
            "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            "Resource": "arn:aws:logs:*:*:*",
        }
    ],
}

ROLES = [
    {
        "name": "BedrockAgentCoreExecutionRole",
        "trust": AGENTCORE_RUNTIME_TRUST,
        "policy": EXECUTION_ROLE_POLICY,
        "description": "Execution role for AgentCore Runtime containers",
    },
    {
        "name": "BedrockAgentCoreGatewayRole",
        "trust": AGENTCORE_RUNTIME_TRUST,
        "policy": GATEWAY_ROLE_POLICY,
        "description": "Role for AgentCore Gateway to invoke Lambda targets",
    },
    {
        "name": "BedrockAgentCoreLambdaRole",
        "trust": LAMBDA_TRUST,
        "policy": LAMBDA_ROLE_POLICY,
        "description": "Execution role for Lambda functions used as Gateway targets",
    },
]


def create_or_update_role(role_cfg: dict) -> str:
    name = role_cfg["name"]
    try:
        resp = iam.create_role(
            RoleName=name,
            AssumeRolePolicyDocument=json.dumps(role_cfg["trust"]),
            Description=role_cfg["description"],
            Tags=[{"Key": "Project", "Value": "bedrock-agentcore-patterns"}],
        )
        role_arn = resp["Role"]["Arn"]
        logger.info("Role created: %s", role_arn)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "EntityAlreadyExists":
            role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{name}"
            logger.info("Role already exists: %s", role_arn)
            # Update trust policy
            iam.update_assume_role_policy(
                RoleName=name,
                PolicyDocument=json.dumps(role_cfg["trust"]),
            )
        else:
            raise

    # Attach / update inline policy
    iam.put_role_policy(
        RoleName=name,
        PolicyName=f"{name}InlinePolicy",
        PolicyDocument=json.dumps(role_cfg["policy"]),
    )
    logger.info("Inline policy attached to %s", name)
    return role_arn


if __name__ == "__main__":
    if not ACCOUNT_ID:
        print("⚠️  AWS_ACCOUNT_ID is not set.")
    else:
        print("🔐 Setting up IAM roles for AgentCore patterns …\n")
        arns = {}
        for role in ROLES:
            arn = create_or_update_role(role)
            arns[role["name"]] = arn
            print(f"  ✅ {role['name']}")
            print(f"     ARN: {arn}\n")
        print("All roles ready!")
