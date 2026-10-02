from datetime import date


def refund_allowed(invoice_date: date, today: date) -> bool:
    """A refund is allowed within the refund window."""
    return (today - invoice_date).days < 30
