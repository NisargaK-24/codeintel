"""Payment service module for processing transactions."""
from typing import Dict, Any


def calculate_tax(amount: float, rate: float) -> float:
    """Calculate tax for a given transaction amount."""
    if rate < 0:
        raise ValueError("Rate must be positive")
    return round(amount * rate, 2)


def unused_payment_helper() -> str:
    """An internal helper that is completely unused in the codebase."""
    multiplier = 42
    return f"helper_result_{multiplier}"


class PaymentService:
    """Service handling payment calculation and refunds."""

    def __init__(self, currency: str = "USD"):
        self.currency = currency
        self._active = True

    @property
    def status(self) -> str:
        """Get service operational status."""
        return "ACTIVE" if self._active else "DISABLED"

    def calculate_payment(self, amount: float, tax_rate: float = 0.05) -> float:
        """Calculate total payable amount including tax."""
        tax = calculate_tax(amount, tax_rate)
        return amount + tax

    def process_refund(self, order_id: str, amount: float) -> Dict[str, Any]:
        """Process customer refund for an order."""
        return {
            "order_id": order_id,
            "refunded": True,
            "amount": amount,
            "currency": self.currency
        }
