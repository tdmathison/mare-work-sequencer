from sync_helpers import other_destination
import hashlib
import io
import json
import os
import time
import zipfile

from app import app, db, build_archive, package
from test_backups import setup_backup_case
from zip_metadata import source_info, generated_info, copied_info, restore_mtime

DATE = (2020, 6, 15, 10, 20, 24)
MTIME = time.mktime((*DATE, 0, 0, -1))


def test_source_timestamps_standard_raw_backup_and_restore():
    client, cid, uid, post = setup_backup_case()
    with app.app_context():
        root = package(cid)
        paths = [
            root / "scripts/decode.py",
            root / "reports/sections/executive_summary.md",
        ]
        from reporting import OUTPUT

        paths.append(root / OUTPUT)
        for path in paths:
            os.utime(path, (MTIME, MTIME))
        os.utime(root / "scripts", (MTIME, MTIME))
        db().execute("UPDATE notes SET include_export=1 WHERE case_id=?", (cid,))
        db().commit()
        for kind in ("standard", "raw"):
            stream, name = build_archive(cid, kind)
            with stream, zipfile.ZipFile(stream) as archive:
                info = archive.getinfo(name + "/scripts/decode.py")
                assert info.date_time == DATE
                assert info.compress_type == zipfile.ZIP_DEFLATED
                assert archive.getinfo(name + "/scripts/").date_time == DATE
                manifest = json.loads(archive.read(name + "/manifest.json"))
                for item in manifest["files"]:
                    content = archive.read(name + "/" + item["path"])
                    assert hashlib.sha256(content).hexdigest() == item["sha256"]
                    assert len(content) == item["size"]
                for generated in ("README.md", "manifest.json"):
                    assert (
                        archive.getinfo(name + "/" + generated).date_time[0]
                        == time.localtime().tm_year
                    )
                if kind == "raw":
                    assert (
                        archive.getinfo(name + "/scripts/decode.py").date_time == DATE
                    )
                    assert (
                        archive.getinfo(
                            name + "/reports/reverse-engineering-notes.md"
                        ).date_time[0]
                        == time.localtime().tm_year
                    )
    response = post(f"/cases/{cid}/backup")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        info = next(
            i
            for i in archive.infolist()
            if i.filename.endswith("/scripts/decode_py.txt")
        )
        assert info.date_time == DATE
        assert info.compress_type == zipfile.ZIP_DEFLATED
        assert archive.read(info) == b"print(42)"
        for suffix in ("/case-data.json", "/manifest.json"):
            assert (
                next(
                    i for i in archive.infolist() if i.filename.endswith(suffix)
                ).date_time[0]
                == time.localtime().tm_year
            )
    other_destination()
    assert (
        post(
            "/import-export/import-raw", backup=(io.BytesIO(response.data), "raw.zip")
        ).status_code
        == 302
    )
    with app.app_context():
        new = db().execute("SELECT max(id) FROM cases").fetchone()[0]
        assert abs((package(new) / "scripts/decode.py").stat().st_mtime - MTIME) <= 2
        assert abs((package(new) / "scripts").stat().st_mtime - MTIME) <= 2
    full = post("/import-export/export")
    assert full.status_code == 200
    with zipfile.ZipFile(io.BytesIO(full.data)) as archive:
        for info in archive.infolist():
            assert info.date_time[0] == time.localtime().tm_year
            assert info.compress_type == zipfile.ZIP_STORED
            assert abs(time.mktime((*info.date_time, 0, 0, -1)) - time.time()) < 60
    other_destination()
    assert (
        post(
            "/import-export/import", backup=(io.BytesIO(full.data), "full.zip")
        ).status_code
        == 302
    )
    with app.app_context():
        restored = db().execute("SELECT max(id) FROM cases").fetchone()[0]
        assert (
            abs((package(restored) / "scripts/decode.py").stat().st_mtime - MTIME) <= 2
        )


def test_copy_does_not_mutate_source_and_preserves_attributes():
    original = generated_info("old.py")
    original.date_time = DATE
    clone = copied_info(original, "old_py.txt")
    assert clone is not original
    assert original.filename == "old.py"
    assert clone.date_time == original.date_time
    assert clone.external_attr == original.external_attr
    assert clone.compress_type == original.compress_type
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        with archive.open(clone, "w") as destination:
            destination.write(b"contents")
    assert original.file_size == 0
    with zipfile.ZipFile(out) as archive:
        assert archive.read("old_py.txt") == b"contents"
        assert archive.getinfo("old_py.txt").file_size == 8


def test_range_handling_and_untrusted_restore(tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"content")
    for year, expected in [(1970, 1980), (2200, 2107)]:
        os.utime(path, (time.mktime((year, 1, 1, 0, 0, 0, 0, 0, -1)),) * 2)
        assert source_info(path, "file").date_time[0] == expected
    os.utime(path, (MTIME + 1, MTIME + 1))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(source_info(path, "file"), b"content")
    with zipfile.ZipFile(out) as archive:
        assert archive.getinfo("file").date_time == DATE
    before = path.stat().st_mtime
    for date in [
        (1980, 1, 1, 0, 0, 0),
        (2020, 2, 31, 0, 0, 0),
        (2107, 12, 31, 23, 59, 58),
    ]:
        info = generated_info("file")
        info.date_time = date
        assert not restore_mtime(path, info)
        assert path.stat().st_mtime == before
    info.date_time = DATE
    assert restore_mtime(path, info)
    assert path.stat().st_mtime == MTIME
    directory = generated_info("folder/")
    assert directory.is_dir() and directory.external_attr & 0x10
