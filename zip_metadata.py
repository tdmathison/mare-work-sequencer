"""ZIP modification times use the deployment host's local timezone (no offset)."""

import copy
import os
import stat
import time
import zipfile


def generated_info(name, compression=zipfile.ZIP_DEFLATED):
    date = time.localtime()[:6]
    if date[0] < 1980:
        date = (1980, 1, 1, 0, 0, 0)
    elif date[0] > 2107:
        date = (2107, 12, 31, 23, 59, 58)
    info = zipfile.ZipInfo(name, date)
    info.compress_type = compression
    info.create_system = 3
    directory = name.endswith("/")
    info.external_attr = (
        (stat.S_IFDIR | 0o755) if directory else (stat.S_IFREG | 0o644)
    ) << 16
    if directory:
        info.external_attr |= 0x10
    return info


def source_info(path, name, compression=zipfile.ZIP_DEFLATED):
    info = zipfile.ZipInfo.from_file(path, arcname=name, strict_timestamps=False)
    info.compress_type = compression
    return info


def copied_info(info, name):
    result = copy.copy(info)
    result.filename = name
    result.orig_filename = name
    return result


def restore_mtime(path, info):
    """Ignore malformed, future (>24 hours), and unrecoverable default dates."""
    date = info.date_time
    if date == (1980, 1, 1, 0, 0, 0) or not 1980 <= date[0] <= 2107:
        return False
    try:
        value = time.mktime((*date, 0, 0, -1))
        if time.localtime(value)[:6] != date or value > time.time() + 86400:
            return False
        os.utime(path, (path.stat().st_atime, value))
        return True
    except (OSError, OverflowError, ValueError):
        return False
