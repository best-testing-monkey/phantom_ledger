"""Margin calculation utilities."""


def compute_margin_required(quantity: float, price: float, margin_pct: float) -> float:
    """Calculate margin required for a position.

    Args:
        quantity: Position size (number of shares/units)
        price: Entry price
        margin_pct: Margin percentage (e.g., 0.1 for 10%)

    Returns:
        Margin required amount
    """
    return quantity * price * margin_pct
