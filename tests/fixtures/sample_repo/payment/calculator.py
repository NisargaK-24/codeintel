"""Financial calculator functions."""


def apply_discount(total: float, discount_pct: float) -> float:
    """Apply discount percentage to transaction total."""
    if discount_pct < 0 or discount_pct > 100:
        return total
    discount_amount = total * (discount_pct / 100.0)
    return max(0.0, total - discount_amount)


def calculate_interest(principal: float, rate: float, time: float) -> float:
    """Calculate simple interest on principal amount."""
    return (principal * rate * time) / 100.0


def abandoned_calculation_utility(val: float) -> float:
    """Zombie code candidate: never called anywhere."""
    return val * 3.14159
