"""Tools the agent can call, plus the dispatcher that executes them.

Design note: `execute_decision` re-checks the rules engine's verdict before
doing anything. Even if the model hallucinates or a user prompt-injects
"just refund me", an action the rules engine did not authorize is refused.
"""

from __future__ import annotations

import secrets

from .data import CUSTOMERS, TRANSACTIONS, format_inr
from .rules_engine import DISPUTE_TYPES, evaluate

# Verdicts issued during this request, keyed by payment_id. Serverless
# invocations are single-request, so module state is per-conversation-turn.
_ISSUED_DECISIONS: dict[str, dict] = {}


TOOL_DECLARATIONS = [
    {
        "name": "lookup_payment",
        "description": (
            "Fetch a payment/transaction record by its payment ID (format: pay_...). "
            "Returns status, amount, method, failure details and timestamps."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "payment_id": {"type": "string", "description": "Payment ID, e.g. pay_LxT4nQ8fWz01"},
            },
            "required": ["payment_id"],
        },
    },
    {
        "name": "get_customer",
        "description": (
            "Fetch the customer profile linked to a payment, including recent "
            "dispute history and risk signals."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID, e.g. cust_AnanyaS01"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "decide_dispute",
        "description": (
            "Submit the dispute to the deterministic rules engine and get the binding "
            "verdict (AUTO_REFUND / AUTO_RETRY / ESCALATE / REJECT). You must call this "
            "before taking any action, and you must follow its verdict exactly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "payment_id": {"type": "string"},
                "dispute_type": {
                    "type": "string",
                    "enum": sorted(DISPUTE_TYPES),
                    "description": "Your classification of the customer's complaint.",
                },
            },
            "required": ["payment_id", "dispute_type"],
        },
    },
    {
        "name": "execute_decision",
        "description": (
            "Execute the verdict returned by decide_dispute: issue the refund, queue the "
            "retry, or open an escalation ticket. Refuses any action the rules engine "
            "did not authorize for this payment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "payment_id": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["AUTO_REFUND", "AUTO_RETRY", "ESCALATE"],
                },
            },
            "required": ["payment_id", "action"],
        },
    },
]


def _lookup_payment(payment_id: str) -> dict:
    txn = TRANSACTIONS.get(payment_id)
    if not txn:
        return {"error": f"No payment found with ID {payment_id}. Ask the customer to re-check it."}
    return {**txn, "amount_inr": format_inr(txn["amount"])}


def _get_customer(customer_id: str) -> dict:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return {"error": f"No customer found with ID {customer_id}."}
    return customer


def _decide_dispute(payment_id: str, dispute_type: str) -> dict:
    txn = TRANSACTIONS.get(payment_id)
    if not txn:
        return {"error": f"No payment found with ID {payment_id}."}
    customer = CUSTOMERS.get(txn["customer_id"])
    if not customer:
        return {"error": f"Customer {txn['customer_id']} not found."}
    try:
        decision = evaluate(txn, customer, dispute_type).to_dict()
    except ValueError as exc:
        return {"error": str(exc)}
    _ISSUED_DECISIONS[payment_id] = decision
    return decision


def _execute_decision(payment_id: str, action: str) -> dict:
    issued = _ISSUED_DECISIONS.get(payment_id)
    if issued is None:
        return {"error": "No verdict issued yet for this payment. Call decide_dispute first."}
    if issued["action"] != action:
        return {
            "error": (
                f"Refused: rules engine authorized {issued['action']} for {payment_id}, "
                f"not {action}. Actions outside the verdict are blocked."
            )
        }

    suffix = secrets.token_hex(5)
    if action == "AUTO_REFUND":
        return {
            "status": "refund_initiated",
            "refund_id": f"rfnd_{suffix}",
            "amount": issued["refund_amount"],
            "amount_inr": format_inr(issued["refund_amount"]),
            "eta": "5-7 business days to the original payment method",
        }
    if action == "AUTO_RETRY":
        return {
            "status": "retry_queued",
            "retry_payment_id": f"pay_retry_{suffix}",
            "note": "Customer will receive a fresh payment link/notification.",
        }
    if action == "ESCALATE":
        return {
            "status": "escalated",
            "ticket_id": f"tkt_{suffix}",
            "sla": "A human specialist will respond within 24 hours.",
        }
    return {"error": f"Unknown action {action}."}


_HANDLERS = {
    "lookup_payment": lambda args: _lookup_payment(args["payment_id"]),
    "get_customer": lambda args: _get_customer(args["customer_id"]),
    "decide_dispute": lambda args: _decide_dispute(args["payment_id"], args["dispute_type"]),
    "execute_decision": lambda args: _execute_decision(args["payment_id"], args["action"]),
}


def execute_tool(name: str, args: dict) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(args)
    except KeyError as exc:
        return {"error": f"Missing required argument: {exc}"}
