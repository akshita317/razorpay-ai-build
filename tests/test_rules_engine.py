"""Unit tests for the deterministic rules engine — every rule, every branch."""

from datetime import datetime, timedelta, timezone

import pytest

from app.rules_engine import (
    AUTO_REFUND_LIMIT_PAISE,
    DISPUTE_ABUSE_THRESHOLD,
    evaluate,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


def txn(**overrides) -> dict:
    base = {
        "payment_id": "pay_test",
        "customer_id": "cust_test",
        "amount": 100_000,
        "status": "captured",
        "failure_code": None,
        "amount_debited": True,
        "retry_count": 0,
        "refund_id": None,
        "created_at": (NOW - timedelta(days=5)).isoformat(),
    }
    base.update(overrides)
    return base


def customer(**overrides) -> dict:
    base = {"customer_id": "cust_test", "disputes_90d": 0, "fraud_score": 0.1, "flagged": False}
    base.update(overrides)
    return base


def test_r1_already_refunded_rejects():
    d = evaluate(txn(status="refunded", refund_id="rfnd_x"), customer(), "ITEM_NOT_RECEIVED", NOW)
    assert (d.action, d.rule_id) == ("REJECT", "R1")


def test_r2_unauthorized_always_escalates():
    d = evaluate(txn(), customer(), "UNAUTHORIZED", NOW)
    assert (d.action, d.rule_id) == ("ESCALATE", "R2")


def test_r3_flagged_customer_escalates():
    d = evaluate(txn(), customer(flagged=True), "ITEM_NOT_RECEIVED", NOW)
    assert (d.action, d.rule_id) == ("ESCALATE", "R3")


def test_r3_high_fraud_score_escalates():
    d = evaluate(txn(), customer(fraud_score=0.9), "ITEM_NOT_RECEIVED", NOW)
    assert (d.action, d.rule_id) == ("ESCALATE", "R3")


def test_r4_debited_but_failed_auto_refunds():
    d = evaluate(
        txn(status="failed", failure_code="BANK_PROCESSING_ERROR", amount_debited=True),
        customer(), "PAYMENT_FAILED", NOW,
    )
    assert (d.action, d.rule_id) == ("AUTO_REFUND", "R4")
    assert d.refund_amount == 100_000


def test_r5_transient_failure_retries():
    d = evaluate(
        txn(status="failed", failure_code="GATEWAY_TIMEOUT", amount_debited=False, retry_count=0),
        customer(), "PAYMENT_FAILED", NOW,
    )
    assert (d.action, d.rule_id) == ("AUTO_RETRY", "R5")


def test_r5_retry_budget_exhausted_falls_through_to_reject():
    d = evaluate(
        txn(status="failed", failure_code="GATEWAY_TIMEOUT", amount_debited=False, retry_count=2),
        customer(), "PAYMENT_FAILED", NOW,
    )
    assert (d.action, d.rule_id) == ("REJECT", "R6")


def test_r6_failed_nothing_debited_rejects():
    d = evaluate(
        txn(status="failed", failure_code="PAYMENT_DECLINED", amount_debited=False),
        customer(), "PAYMENT_FAILED", NOW,
    )
    assert (d.action, d.rule_id) == ("REJECT", "R6")


def test_r7_outside_refund_window_rejects():
    d = evaluate(
        txn(created_at=(NOW - timedelta(days=200)).isoformat()),
        customer(), "ITEM_NOT_RECEIVED", NOW,
    )
    assert (d.action, d.rule_id) == ("REJECT", "R7")


def test_r8_dispute_abuse_escalates():
    d = evaluate(txn(), customer(disputes_90d=DISPUTE_ABUSE_THRESHOLD), "ITEM_NOT_RECEIVED", NOW)
    assert (d.action, d.rule_id) == ("ESCALATE", "R8")


def test_r9_above_auto_limit_escalates():
    d = evaluate(txn(amount=AUTO_REFUND_LIMIT_PAISE + 1), customer(), "QUALITY_ISSUE", NOW)
    assert (d.action, d.rule_id) == ("ESCALATE", "R9")


def test_r10_clean_small_captured_auto_refunds():
    d = evaluate(txn(), customer(), "ITEM_NOT_RECEIVED", NOW)
    assert (d.action, d.rule_id) == ("AUTO_REFUND", "R10")
    assert d.refund_amount == 100_000


def test_rule_order_fraud_beats_window():
    """A flagged customer escalates even when the refund would also be out of window."""
    d = evaluate(
        txn(created_at=(NOW - timedelta(days=400)).isoformat()),
        customer(flagged=True), "ITEM_NOT_RECEIVED", NOW,
    )
    assert d.rule_id == "R3"


def test_unknown_dispute_type_raises():
    with pytest.raises(ValueError):
        evaluate(txn(), customer(), "NOT_A_REAL_TYPE", NOW)
