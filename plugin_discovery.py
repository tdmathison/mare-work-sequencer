"""Read operator-installed packages into the existing draft registry; never import code."""

import os
from pathlib import Path
import stat
import plugin_store as store


def package_files(folder):
    entries = {}
    total = 0
    root_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for current, directories, filenames, fd in os.fwalk(
            ".", dir_fd=root_fd, follow_symlinks=False
        ):
            prefix = "" if current == "." else current.removeprefix("./") + "/"
            for name in list(directories):
                if name.casefold() in store.RESERVED:
                    directories.remove(name)
                    continue
                if stat.S_ISLNK(
                    os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode
                ):
                    raise ValueError("Symbolic links are not supported.")
                path = store.safe_path(prefix + name)
                entries[path] = {"body": b"", "directory": True}
            for name in filenames:
                if name.casefold() in store.RESERVED:
                    continue
                path = store.safe_path(prefix + name)
                item_fd = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
                )
                try:
                    info = os.fstat(item_fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_size > store.MAX_FILE:
                        raise ValueError("Unsupported or oversized package file.")
                    with os.fdopen(item_fd, "rb", closefd=False) as source:
                        body = source.read(store.MAX_FILE + 1)
                finally:
                    os.close(item_fd)
                total += len(body)
                if total > store.MAX_TOTAL or len(body) > store.MAX_FILE:
                    raise ValueError("Package exceeds size limits.")
                entries[path] = {"body": body, "directory": False}
            if len(entries) > store.MAX_FILES:
                raise ValueError("Package contains too many entries.")
        store.validate_tree(entries)
        checked = store.static_validation(entries)
        if not checked["valid"]:
            raise ValueError(
                "; ".join(d["message"] for d in checked["diagnostics"][:5])
            )
        return entries, checked["manifest"]
    finally:
        os.close(root_fd)


def discover(root):
    root = Path(root)
    if not root.exists():
        return [], []
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Configured plugin directory must be a real directory.")
    packages = []
    invalid = []
    with os.scandir(root) as source:
        count = 0
        for item in source:
            count += 1
            if count > 200:
                invalid.append(
                    {
                        "package": "plugins",
                        "error": "Directory scan limited to 200 entries.",
                    }
                )
                break
            if item.name.startswith(".") or not item.is_dir(follow_symlinks=False):
                continue
            folder = Path(item.path)
            if (
                not (folder / "plugin.json").exists()
                and not (folder / "plugin.json").is_symlink()
            ):
                continue
            try:
                entries, value = package_files(folder)
                packages.append((item.name, entries, value))
            except (ValueError, OSError, UnicodeError) as error:
                invalid.append({"package": item.name, "error": str(error)[:500]})
    return packages, invalid


def retire_package(root, location, pid):
    """Move one recorded installed package to recovery without following symlinks.

    No recursive removal occurs, so even nested symlinks cannot escape the root.
    Returns a rollback callback for a failed registry transaction.
    """
    import json
    import uuid

    if not isinstance(location, str) or location in (".", "..") or not location or any(
        char in location for char in ("/", "\\", "\0")
    ) or location.startswith("."):
        raise ValueError("Unsafe installed package location.")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    trash_fd = None
    try:
        try:
            info = os.stat(location, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            os.close(root_fd)
            return lambda rollback=False: None  # Already removed by the operator; unregister safely.
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Installed package must be a real directory.")
        package_fd = os.open(location, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            manifest_fd = os.open("plugin.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=package_fd)
            with os.fdopen(manifest_fd, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise ValueError("Installed manifest must be a regular file.")
                raw = source.read(store.MAX_FILE + 1)
                value = json.loads(raw) if len(raw) <= store.MAX_FILE else None
                if not isinstance(value, dict) or value.get("id") != pid:
                    raise ValueError("Installed package identifier no longer matches its registration.")
        finally:
            os.close(package_fd)
        try:
            os.mkdir(".mws-deleted", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        trash_fd = os.open(".mws-deleted", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        destination = pid + "-" + uuid.uuid4().hex
        os.rename(location, destination, src_dir_fd=root_fd, dst_dir_fd=trash_fd)
    except Exception:
        if trash_fd is not None:
            os.close(trash_fd)
        os.close(root_fd)
        raise

    def finish(rollback=False):
        try:
            if rollback:
                os.rename(destination, location, src_dir_fd=trash_fd, dst_dir_fd=root_fd)
        finally:
            os.close(trash_fd)
            os.close(root_fd)
    return finish
