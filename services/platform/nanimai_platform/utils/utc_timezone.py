from datetime import UTC, datetime


def to_utc_timestamp(dt: datetime) -> int:
    """Returns Unix timestamp (int), ensuring datetime is UTC"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp())
