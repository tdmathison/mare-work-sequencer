"""Names for multi-category backup downloads; independent of archive contents."""
from datetime import datetime
from zoneinfo import ZoneInfo

from backup_areas import selection

EXPORT_IDENTIFIERS = (("cases", "C"), ("tags", "T"), ("actors", "TA"), ("families", "MF"))


def archive_filename(areas, timezone_name=None, *, started_at=None):
    chosen, _ = selection(list(areas))
    zone = ZoneInfo(timezone_name) if timezone_name else None
    # None uses the server's local timezone. Existing queued jobs can use their
    # persisted start instant rather than the time a download is requested.
    moment = datetime.now(zone) if started_at is None else started_at.astimezone(zone)
    suffix = "_".join(identifier for area, identifier in EXPORT_IDENTIFIERS if area in chosen)
    return f"MWS_{moment.strftime('%Y%m%d-%H%M%S')}_{suffix}.zip"
