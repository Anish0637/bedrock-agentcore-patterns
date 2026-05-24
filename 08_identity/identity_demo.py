"""
Pattern 8 — AgentCore Identity
================================
Demonstrates:
  1. Creating a WorkloadIdentity (agent IAM identity)
  2. Creating a CredentialProvider (OAuth 2-legged for an external service)
  3. Token exchange: user OIDC token → workload access token
  4. Attribute-Based Access Control (ABAC) via resource tags

Usage:
    python identity_demo.py
"""

import os
import json
import logging
import boto3
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID")


def get_client():
    return boto3.client("bedrock-agentcore", region_name=REGION)


# ── 1. Workload Identity ───────────────────────────────────────────────────────

def create_workload_identity(client, name: str, team: str) -> str:
    """Register a workload identity for an agent."""
    logger.info("Creating workload identity: %s", name)
    response = client.create_workload_identity(
        name=name,
        description=f"Workload identity for {name} agent",
        tags={"Owner": team, "Environment": "production", "Project": "bedrock-agentcore"},
    )
    identity_id = response["workloadIdentityId"]
    logger.info("Workload identity created: %s", identity_id)
    return identity_id


def get_workload_token(client, identity_id: str, user_token: str) -> str:
    """Exchange a user OIDC token for a workload access token."""
    logger.info("Exchanging token for workload identity: %s", identity_id)
    response = client.get_token(
        workloadIdentityId=identity_id,
        userToken=user_token,
    )
    workload_token = response["accessToken"]
    logger.info("Workload token obtained (expires: %s)", response.get("expiresAt"))
    return workload_token


# ── 2. OAuth Credential Provider (2-legged) ────────────────────────────────────

def create_oauth2lo_credential_provider(
    client,
    name: str,
    client_id: str,
    client_secret_arn: str,
    token_url: str,
    scopes: list[str],
) -> str:
    """Create a 2-legged OAuth credential provider for external service access."""
    logger.info("Creating OAuth2LO credential provider: %s", name)
    response = client.create_oauth2_credential_provider(
        name=name,
        description="OAuth 2-legged credential provider for external service",
        credentialProviderConfiguration={
            "oauth2": {
                "grantType": "CLIENT_CREDENTIALS",
                "clientId": client_id,
                "clientSecretArn": client_secret_arn,
                "tokenUrl": token_url,
                "scopes": scopes,
            }
        },
        tags={"Environment": "production"},
    )
    provider_id = response["credentialProviderId"]
    logger.info("Credential provider created: %s", provider_id)
    return provider_id


# ── 3. ABAC policy example ──────────────────────────────────────────────────────

ABAC_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowAccessToOwnedWorkloadIdentities",
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:GetWorkloadIdentity",
                "bedrock-agentcore:UpdateWorkloadIdentity",
                "bedrock-agentcore:GetToken",
            ],
            "Resource": "*",
            "Condition": {
                "StringEquals": {
                    # Only allow access if the resource tag 'Owner' matches the caller's
                    # principal tag 'Team' — classic ABAC pattern
                    "bedrock-agentcore:ResourceTag/Owner": "${aws:PrincipalTag/Team}"
                }
            },
        },
        {
            "Sid": "DenyNonProductionCredentialProviders",
            "Effect": "Deny",
            "Action": ["bedrock-agentcore:GetCredential"],
            "Resource": "*",
            "Condition": {
                "StringNotEquals": {
                    "bedrock-agentcore:ResourceTag/Environment": "production"
                }
            },
        },
    ],
}


def print_abac_policy():
    """Print the ABAC IAM policy that enforces tag-based access control."""
    print("\n📋 ABAC IAM Policy (attach to principal role):")
    print(json.dumps(ABAC_POLICY, indent=2))


# ── 4. List and clean up ───────────────────────────────────────────────────────

def list_workload_identities(client) -> list:
    response = client.list_workload_identities()
    identities = response.get("workloadIdentities", [])
    logger.info("Found %d workload identities", len(identities))
    return identities


def delete_workload_identity(client, identity_id: str):
    try:
        client.delete_workload_identity(workloadIdentityId=identity_id)
        logger.info("Deleted workload identity: %s", identity_id)
    except Exception as exc:
        logger.error("Failed to delete %s: %s", identity_id, exc)


# ── Main demo ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not ACCOUNT_ID:
        print("⚠️  AWS_ACCOUNT_ID is not set in .env")
    else:
        client = get_client()

        # Show the ABAC policy
        print_abac_policy()

        # Create a workload identity for the calendar agent
        try:
            identity_id = create_workload_identity(
                client,
                name="calendar-scheduler-agent",
                team="platform-engineering",
            )

            # List all workload identities
            identities = list_workload_identities(client)
            for i in identities:
                print(f"  • {i.get('name')} — {i.get('workloadIdentityId')}")

            # Clean up demo resource
            delete_workload_identity(client, identity_id)
            print("\n✅ Identity demo complete — workload identity cleaned up.")

        except Exception as exc:
            logger.error("Identity demo failed: %s", exc)
            print("\n⚠️  Some operations require actual AWS credentials with AgentCore permissions.")
