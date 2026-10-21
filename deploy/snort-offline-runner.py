#!/usr/bin/env python3
"""Admin-owned Linux/bubblewrap isolation contract; never run as root."""
import os
from pathlib import Path
import resource
import sys

if sys.platform != "linux" or os.geteuid() == 0:
    raise SystemExit("Requires an unprivileged Linux account.")
engine, profile, work = map(lambda p: Path(p).resolve(), sys.argv[1:4])
if not engine.is_relative_to("/usr") or not profile.is_file() or not work.is_dir():
    raise SystemExit("Invalid trusted engine/profile/work configuration.")
if any(work.is_relative_to(p) for p in ("/usr", "/bin", "/lib", "/lib64", "/sbin")):
    raise SystemExit("Application/job data must be outside runtime mounts.")
if (
    str(profile.parent) in ("/", "/etc", "/var", "/var/lib", "/home", "/tmp", "/usr")
    or work.is_relative_to(profile.parent)
    or (profile.parent / "mare.db").exists()
):
    raise SystemExit("Use a dedicated profile-only directory.")
for key, value in [
    (resource.RLIMIT_CPU, 60),
    (resource.RLIMIT_AS, 2 * 1024**3),
    (resource.RLIMIT_FSIZE, 16 * 1024**2),
    (resource.RLIMIT_NOFILE, 128),
    (resource.RLIMIT_CORE, 0),
]:
    resource.setrlimit(key, (value, value))
args = [
    "/usr/bin/bwrap",
    "--unshare-all",
    "--die-with-parent",
    "--new-session",
    "--cap-drop",
    "ALL",
    "--proc",
    "/proc",
    "--dev",
    "/dev",
    "--tmpfs",
    "/tmp",
]
for p in ("/usr", "/bin", "/sbin", "/lib", "/lib64"):
    if Path(p).exists():
        args += ["--ro-bind", p, p]
args += [
    "--ro-bind",
    str(profile.parent),
    "/profile",
    "--bind",
    str(work),
    "/work",
    "--ro-bind",
    str(work / "current.rules"),
    "/work/current.rules",
]
for p in work.glob("*.pcap"):
    args += ["--ro-bind", str(p), "/work/" + p.name]
args += ["--chdir", "/work", "--", str(engine), *sys.argv[4:]]
os.execv(args[0], args)
