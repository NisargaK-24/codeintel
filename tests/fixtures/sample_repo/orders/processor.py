"""Order processing module with cross-module dependencies."""
from typing import Dict, Any, List
from payment.service import PaymentService
from payment.calculator import apply_discount


def unused_cart_cleaner() -> None:
    """Zombie code candidate in orders module."""
    items = []
    items.clear()


class OrderProcessor:
    """Coordinates cart checkout and payment processing."""

    def __init__(self):
        self.service = PaymentService()

    def process_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process an individual order by calling PaymentService."""
        subtotal = float(order_data.get("subtotal", 0.0))
        discount = float(order_data.get("discount", 0.0))
        discounted = apply_discount(subtotal, discount)
        total = self.service.calculate_payment(discounted)
        return {
            "order_id": order_data.get("id"),
            "total": total,
            "status": "PROCESSED"
        }

    def checkout(self, cart_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Entry point for customer checkout calling process_order."""
        subtotal = sum(float(item.get("price", 0.0)) for item in cart_items)
        order = {"id": "ORD-12345", "subtotal": subtotal, "discount": 10.0}
        return self.process_order(order)
