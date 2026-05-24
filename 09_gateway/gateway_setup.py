"""
Pattern 9 — AgentCore Gateway: Lambda Functions as MCP Tools
=============================================================
Steps:
  1. Create (or use existing) AWS Lambda function with order management tools
  2. Create an AgentCore Gateway
  3. Register the Lambda as a Gateway Target with tool schema
  4. Invoke the gateway via MCP from a Strands agent

Usage:
    python gateway_setup.py    # Creates gateway + target (run once)
    python gateway_client.py   # Invokes tools through the gateway
"""

import os
import json
import zipfile
import logging
import boto3
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID")
GATEWAY_ID = os.getenv("GATEWAY_ID", "")


# ── Lambda function source (inline zip) ───────────────────────────────────────

LAMBDA_SOURCE = '''
import json
import logging

logger = logging.getLogger(__name__)

# Simulated order database
ORDERS = {
    "ORD-001": {"id": "ORD-001", "status": "shipped",   "item": "Laptop",    "qty": 1, "total": 1299.99},
    "ORD-002": {"id": "ORD-002", "status": "pending",   "item": "Keyboard",  "qty": 2, "total":  149.98},
    "ORD-003": {"id": "ORD-003", "status": "delivered", "item": "Monitor",   "qty": 1, "total":  499.99},
    "ORD-004": {"id": "ORD-004", "status": "cancelled", "item": "Headphones","qty": 1, "total":  249.99},
}


def get_tool_name(context) -> str:
    """Extract the tool name from AgentCore Gateway context."""
    try:
        return context.client_context.custom.get("bedrockagentcoreToolName", "unknown")
    except AttributeError:
        return "unknown"


def handle_get_order(order_id: str) -> dict:
    order = ORDERS.get(order_id)
    if order:
        return {"success": True, "order": order}
    return {"success": False, "error": f"Order {order_id} not found"}


def handle_update_order(order_id: str, status: str) -> dict:
    valid_statuses = {"pending", "processing", "shipped", "delivered", "cancelled"}
    if status not in valid_statuses:
        return {"success": False, "error": f"Invalid status. Must be one of: {valid_statuses}"}
    if order_id not in ORDERS:
        return {"success": False, "error": f"Order {order_id} not found"}
    ORDERS[order_id]["status"] = status
    return {"success": True, "order_id": order_id, "new_status": status}


def handle_list_orders(status_filter: str | None = None) -> dict:
    orders = list(ORDERS.values())
    if status_filter:
        orders = [o for o in orders if o["status"] == status_filter]
    return {"success": True, "orders": orders, "count": len(orders)}


def lambda_handler(event, context):
    logger.info("Event: %s", json.dumps(event, default=str))
    tool_name = get_tool_name(context)
    logger.info("Tool invoked: %s", tool_name)

    try:
        if tool_name == "get_order_tool":
            order_id = event.get("orderId", "")
            return handle_get_order(order_id)

        elif tool_name == "update_order_tool":
            order_id = event.get("orderId", "")
            status   = event.get("status", "")
            return handle_update_order(order_id, status)

        elif tool_name == "list_orders_tool":
            status_filter = event.get("statusFilter")
            return handle_list_orders(status_filter)

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    except Exception as exc:
        logger.error("Tool execution failed: %s", exc)
        return {"success": False, "error": str(exc)}
'''


def create_lambda_zip() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("lambda_function.py", LAMBDA_SOURCE)
    return buffer.getvalue()


def deploy_lambda(lambda_client, role_arn: str) -> str:
    fn_name = "AgentCoreGatewayOrderTools"
    zip_bytes = create_lambda_zip()

    try:
        resp = lambda_client.get_function(FunctionName=fn_name)
        # Update if exists
        lambda_client.update_function_code(FunctionName=fn_name, ZipFile=zip_bytes)
        fn_arn = resp["Configuration"]["FunctionArn"]
        logger.info("Lambda updated: %s", fn_arn)
    except lambda_client.exceptions.ResourceNotFoundException:
        resp = lambda_client.create_function(
            FunctionName=fn_name,
            Runtime="python3.12",
            Role=role_arn,
            Handler="lambda_function.lambda_handler",
            Code={"ZipFile": zip_bytes},
            Description="AgentCore Gateway order management tools",
            Timeout=30,
            MemorySize=256,
        )
        fn_arn = resp["FunctionArn"]
        logger.info("Lambda created: %s", fn_arn)

    return fn_arn


def create_gateway(agentcore_client, name: str) -> str:
    try:
        resp = agentcore_client.create_gateway(
            name=name,
            description="Pattern 9: Gateway exposing Lambda order tools via MCP",
            roleArn=f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentCoreGatewayRole",
        )
        gw_id = resp["gatewayId"]
        logger.info("Gateway created: %s", gw_id)
        return gw_id
    except Exception as exc:
        logger.error("Gateway creation failed: %s", exc)
        raise


def register_lambda_target(agentcore_client, gateway_id: str, lambda_arn: str) -> str:
    target_config = {
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {
                    "inlinePayload": [
                        {
                            "name": "get_order_tool",
                            "description": "Retrieve order details by order ID",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"orderId": {"type": "string", "description": "Order ID (e.g. ORD-001)"}},
                                "required": ["orderId"],
                            },
                        },
                        {
                            "name": "update_order_tool",
                            "description": "Update the status of an existing order",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "orderId": {"type": "string"},
                                    "status": {
                                        "type": "string",
                                        "enum": ["pending", "processing", "shipped", "delivered", "cancelled"],
                                    },
                                },
                                "required": ["orderId", "status"],
                            },
                        },
                        {
                            "name": "list_orders_tool",
                            "description": "List all orders, optionally filtered by status",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "statusFilter": {
                                        "type": "string",
                                        "enum": ["pending", "processing", "shipped", "delivered", "cancelled"],
                                    }
                                },
                            },
                        },
                    ]
                },
            }
        }
    }

    resp = agentcore_client.create_gateway_target(
        gatewayIdentifier=gateway_id,
        name="OrderManagementTarget",
        description="Lambda-backed order management tools",
        targetConfiguration=target_config,
        credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
    )
    target_id = resp["gatewayTargetId"]
    logger.info("Gateway target registered: %s", target_id)
    return target_id


if __name__ == "__main__":
    if not ACCOUNT_ID:
        print("⚠️  AWS_ACCOUNT_ID is not set.")
    else:
        lambda_client = boto3.client("lambda", region_name=REGION)
        agentcore_client = boto3.client("bedrock-agentcore", region_name=REGION)

        lambda_role = f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentCoreLambdaRole"
        fn_arn = deploy_lambda(lambda_client, lambda_role)

        gw_id = create_gateway(agentcore_client, "OrderManagementGateway")
        target_id = register_lambda_target(agentcore_client, gw_id, fn_arn)

        print("\n✅ Gateway setup complete!")
        print(f"   Gateway ID  : {gw_id}")
        print(f"   Target ID   : {target_id}")
        print(f"   Lambda ARN  : {fn_arn}")
        print(f"\nAdd to .env: GATEWAY_ID={gw_id}")
