"""Mock payment-gateway data store.

Stands in for the transactions / customers services a real support agent
would query. IDs follow Razorpay-style prefixes (pay_, cust_, rfnd_) so the
demo reads like production data, but every record here is synthetic.

Amounts are stored in paise (1/100 INR), matching gateway convention.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


CUSTOMERS: dict[str, dict] = {
    "cust_AnanyaS01": {
        "customer_id": "cust_AnanyaS01",
        "name": "Ananya Sharma",
        "email": "ananya.s@example.com",
        "member_since": _days_ago(540),
        "disputes_90d": 0,
        "fraud_score": 0.08,
        "flagged": False,
    },
    "cust_RohitV02": {
        "customer_id": "cust_RohitV02",
        "name": "Rohit Verma",
        "email": "rohit.v@example.com",
        "member_since": _days_ago(300),
        "disputes_90d": 1,
        "fraud_score": 0.12,
        "flagged": False,
    },
    "cust_MeeraI03": {
        "customer_id": "cust_MeeraI03",
        "name": "Meera Iyer",
        "email": "meera.i@example.com",
        "member_since": _days_ago(800),
        "disputes_90d": 0,
        "fraud_score": 0.05,
        "flagged": False,
    },
    "cust_DevM04": {
        "customer_id": "cust_DevM04",
        "name": "Dev Malhotra",
        "email": "dev.m@example.com",
        "member_since": _days_ago(45),
        "disputes_90d": 2,
        "fraud_score": 0.91,
        "flagged": True,
    },
    "cust_PriyaN05": {
        "customer_id": "cust_PriyaN05",
        "name": "Priya Nair",
        "email": "priya.n@example.com",
        "member_since": _days_ago(200),
        "disputes_90d": 4,
        "fraud_score": 0.31,
        "flagged": False,
    },
}


TRANSACTIONS: dict[str, dict] = {
    # Small captured payment, clean customer -> auto-refund territory
    "pay_LxT4nQ8fWz01": {
        "payment_id": "pay_LxT4nQ8fWz01",
        "order_id": "order_9dKfLm21",
        "customer_id": "cust_AnanyaS01",
        "amount": 129900,
        "currency": "INR",
        "status": "captured",
        "method": "upi",
        "description": "Wireless headphones - MegaKart order",
        "created_at": _days_ago(12),
        "failure_code": None,
        "amount_debited": True,
        "retry_count": 0,
        "refund_id": None,
    },
    # High-value captured payment -> above auto-refund limit
    "pay_MnB7cK2dRv02": {
        "payment_id": "pay_MnB7cK2dRv02",
        "order_id": "order_2xVbNq88",
        "customer_id": "cust_RohitV02",
        "amount": 1850000,
        "currency": "INR",
        "status": "captured",
        "method": "card",
        "description": "Smartphone - MegaKart order",
        "created_at": _days_ago(5),
        "failure_code": None,
        "amount_debited": True,
        "retry_count": 0,
        "refund_id": None,
    },
    # Failed with transient gateway error, nothing debited -> retry
    "pay_QwE9rT5yUi03": {
        "payment_id": "pay_QwE9rT5yUi03",
        "order_id": "order_7pQrSt45",
        "customer_id": "cust_AnanyaS01",
        "amount": 74900,
        "currency": "INR",
        "status": "failed",
        "method": "upi",
        "description": "Yoga mat + blocks - MegaKart order",
        "created_at": _days_ago(0),
        "failure_code": "GATEWAY_TIMEOUT",
        "amount_debited": False,
        "retry_count": 0,
        "refund_id": None,
    },
    # Failed but customer's account was debited -> reversal refund
    "pay_ZaS3xD6cFv04": {
        "payment_id": "pay_ZaS3xD6cFv04",
        "order_id": "order_4mNbVc12",
        "customer_id": "cust_MeeraI03",
        "amount": 219900,
        "currency": "INR",
        "status": "failed",
        "method": "netbanking",
        "description": "Standing desk - MegaKart order",
        "created_at": _days_ago(1),
        "failure_code": "BANK_PROCESSING_ERROR",
        "amount_debited": True,
        "retry_count": 1,
        "refund_id": None,
    },
    # Already refunded -> duplicate refund request
    "pay_PoI8uY4tRe05": {
        "payment_id": "pay_PoI8uY4tRe05",
        "order_id": "order_5tGhJk67",
        "customer_id": "cust_RohitV02",
        "amount": 349900,
        "currency": "INR",
        "status": "refunded",
        "method": "card",
        "description": "Running shoes - MegaKart order",
        "created_at": _days_ago(20),
        "failure_code": None,
        "amount_debited": True,
        "retry_count": 0,
        "refund_id": "rfnd_Xk2mPq91Lz",
    },
    # Captured long ago -> outside refund window
    "pay_KjH2gF7dSa06": {
        "payment_id": "pay_KjH2gF7dSa06",
        "order_id": "order_8wErTy34",
        "customer_id": "cust_MeeraI03",
        "amount": 89900,
        "currency": "INR",
        "status": "captured",
        "method": "upi",
        "description": "Bedsheet set - MegaKart order",
        "created_at": _days_ago(220),
        "failure_code": None,
        "amount_debited": True,
        "retry_count": 0,
        "refund_id": None,
    },
    # Flagged / high fraud-score customer -> always a human
    "pay_VbN6mQ1wEr07": {
        "payment_id": "pay_VbN6mQ1wEr07",
        "order_id": "order_1aZxCv56",
        "customer_id": "cust_DevM04",
        "amount": 45900,
        "currency": "INR",
        "status": "captured",
        "method": "card",
        "description": "Power bank - MegaKart order",
        "created_at": _days_ago(3),
        "failure_code": None,
        "amount_debited": True,
        "retry_count": 0,
        "refund_id": None,
    },
    # Customer with heavy recent dispute history -> human review
    "pay_CxZ5lK9jHg08": {
        "payment_id": "pay_CxZ5lK9jHg08",
        "order_id": "order_6uIoPl90",
        "customer_id": "cust_PriyaN05",
        "amount": 129000,
        "currency": "INR",
        "status": "captured",
        "method": "upi",
        "description": "Mixer grinder - MegaKart order",
        "created_at": _days_ago(8),
        "failure_code": None,
        "amount_debited": True,
        "retry_count": 0,
        "refund_id": None,
    },
    # Hard decline, nothing debited, retries exhausted -> nothing owed
    "pay_TrE1wQ8zXc09": {
        "payment_id": "pay_TrE1wQ8zXc09",
        "order_id": "order_3sDfGh78",
        "customer_id": "cust_RohitV02",
        "amount": 55000,
        "currency": "INR",
        "status": "failed",
        "method": "card",
        "description": "Board game - MegaKart order",
        "created_at": _days_ago(2),
        "failure_code": "PAYMENT_DECLINED",
        "amount_debited": False,
        "retry_count": 2,
        "refund_id": None,
    },
    # Small duplicate charge -> auto-refund territory
    "pay_GfD4sA7pLm10": {
        "payment_id": "pay_GfD4sA7pLm10",
        "order_id": "order_9dKfLm21",
        "customer_id": "cust_AnanyaS01",
        "amount": 49900,
        "currency": "INR",
        "status": "captured",
        "method": "upi",
        "description": "Phone case - MegaKart order (possible duplicate)",
        "created_at": _days_ago(4),
        "failure_code": None,
        "amount_debited": True,
        "retry_count": 0,
        "refund_id": None,
    },
}


def format_inr(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"
