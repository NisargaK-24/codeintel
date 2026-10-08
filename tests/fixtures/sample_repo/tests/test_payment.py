"""Test suite for sample repository."""
from payment.service import PaymentService, calculate_tax


def test_calculate_tax():
    """Verify tax calculation function."""
    assert calculate_tax(100.0, 0.1) == 10.0


def test_payment_service():
    """Verify PaymentService instance methods."""
    srv = PaymentService()
    assert srv.calculate_payment(100.0, 0.05) == 105.0
    refund = srv.process_refund("ORD-1", 50.0)
    assert refund["refunded"] is True
