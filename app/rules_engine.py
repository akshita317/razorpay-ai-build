"""Deterministic dispute-resolution rules engine.

This module — not the LLM — makes every money-movement decision. The agent
may look up data, classify the customer's complaint into a dispute type, and
draft the reply, but the verdict (refund / retry / escalate / reject) comes
from the ordered rules below, first match wins. That keeps decisions
auditable, unit-testable, and immune to prompt injection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

# --- Policy knobs (would live in config / an admin console in production) ---
AUTO_REFUND_LIMIT_PAISE = 500_000        # ₹5,000
REFUND_WINDOW_DAYS = 180
MAX_AUTO_RETRIES = 2
FRAUD_SCORE_THRESHOLD = 0.85
DISPUTE_ABUSE_THRESHOLD = 3              # disputes in last 90 days

TRANSIENT_FAILURE_CODES = {
    "GATEWAY_TIMEOUT",
    "BANK_UNAVAILABLE",
    "NETWORK_ERROR",
}

DISPUTE_TYPES = {
    "ITEM_NOT_RECEIVED",
    "DUPLICATE_CHARGE",
    "PAYMENT_FAILED",
    "UNAUTHORIZED",
    "QUALITY_ISSUE",
}

ACTIONS = {"AUTO_REFUND", "AUTO_RETRY", "ESCALATE", "REJECT"}


@dataclass
class Decision:
    action: str          # one of ACTIONS
    rule_id: str         # which rule fired, e.g. "R7"
    reason_code: str     # machine-readable, e.g. "OUTSIDE_REFUND_WINDOW"
    rationale: str       # human-readable explanation
    refund_amount: int | None = None  # paise, set only for AUTO_REFUND

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate(
    txn: dict,
    customer: dict,
    dispute_type: str,
    now: datetime | None = None,
) -> Decision:
    """Apply ordered rules R1..R10 to a dispute. First match wins."""
    if dispute_type not in DISPUTE_TYPES:
        raise ValueError(f"Unknown dispute type: {dispute_type}")

    now = now or datetime.now(timezone.utc)
    age_days = (now - datetime.fromisoformat(txn["created_at"])).days

    # R1 — a refund already exists; never refund twice.
    if txn["status"] == "refunded":
        return Decision(
            action="REJECT",
            rule_id="R1",
            reason_code="ALREADY_REFUNDED",
            rationale=f"Refund {txn['refund_id']} was already issued for this payment.",
        )

    # R2 — claims of unauthorized use always go to a human (potential fraud/chargeback).
    if dispute_type == "UNAUTHORIZED":
        return Decision(
            action="ESCALATE",
            rule_id="R2",
            reason_code="FRAUD_CLAIM",
            rationale="Unauthorized-transaction claims require human fraud review.",
        )

    # R3 — flagged or high-fraud-score accounts never get automated outcomes.
    if customer["flagged"] or customer["fraud_score"] >= FRAUD_SCORE_THRESHOLD:
        return Decision(
            action="ESCALATE",
            rule_id="R3",
            reason_code="HIGH_RISK_ACCOUNT",
            rationale=(
                f"Customer risk profile (fraud score {customer['fraud_score']:.2f}, "
                f"flagged={customer['flagged']}) requires manual review."
            ),
        )

    # R4 — payment failed but money left the customer's account: reverse it.
    if txn["status"] == "failed" and txn["amount_debited"]:
        return Decision(
            action="AUTO_REFUND",
            rule_id="R4",
            reason_code="DEBITED_NOT_CAPTURED",
            rationale="Payment failed after the customer's account was debited; the debit must be reversed.",
            refund_amount=txn["amount"],
        )

    # R5 — transient failure with retry budget left: retry, don't refund.
    if (
        txn["status"] == "failed"
        and txn["failure_code"] in TRANSIENT_FAILURE_CODES
        and txn["retry_count"] < MAX_AUTO_RETRIES
    ):
        return Decision(
            action="AUTO_RETRY",
            rule_id="R5",
            reason_code="TRANSIENT_FAILURE",
            rationale=(
                f"Failure code {txn['failure_code']} is transient and "
                f"{MAX_AUTO_RETRIES - txn['retry_count']} automatic retries remain."
            ),
        )

    # R6 — payment failed and nothing was debited: there is nothing to refund.
    if txn["status"] == "failed":
        return Decision(
            action="REJECT",
            rule_id="R6",
            reason_code="NO_AMOUNT_CAPTURED",
            rationale="The payment failed and no amount was debited, so no refund is due.",
        )

    # R7 — captured too long ago.
    if age_days > REFUND_WINDOW_DAYS:
        return Decision(
            action="REJECT",
            rule_id="R7",
            reason_code="OUTSIDE_REFUND_WINDOW",
            rationale=f"Payment is {age_days} days old, beyond the {REFUND_WINDOW_DAYS}-day refund window.",
        )

    # R8 — unusually frequent disputes: a human should look at the pattern.
    if customer["disputes_90d"] >= DISPUTE_ABUSE_THRESHOLD:
        return Decision(
            action="ESCALATE",
            rule_id="R8",
            reason_code="DISPUTE_FREQUENCY",
            rationale=(
                f"Customer has {customer['disputes_90d']} disputes in the last 90 days "
                f"(threshold {DISPUTE_ABUSE_THRESHOLD}); routing to manual review."
            ),
        )

    # R9 — amount above the automation limit.
    if txn["amount"] > AUTO_REFUND_LIMIT_PAISE:
        return Decision(
            action="ESCALATE",
            rule_id="R9",
            reason_code="ABOVE_AUTO_LIMIT",
            rationale=(
                f"Amount {txn['amount']} paise exceeds the auto-refund limit of "
                f"{AUTO_REFUND_LIMIT_PAISE} paise; a human must approve."
            ),
        )

    # R10 — captured, in window, clean customer, small amount: refund it.
    return Decision(
        action="AUTO_REFUND",
        rule_id="R10",
        reason_code="WITHIN_POLICY",
        rationale="Captured payment within the refund window, clean customer history, amount under the auto limit.",
        refund_amount=txn["amount"],
    )
