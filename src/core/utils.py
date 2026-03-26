from datetime import datetime


def parse_timestamp(ts) -> datetime | None:
    """
    Safely converts a timestamp value to a datetime object.
    Handles str, datetime, and None inputs; returns None on parse failure.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None
