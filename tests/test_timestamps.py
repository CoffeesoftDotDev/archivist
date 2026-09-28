import ctypes
import errno
import io
import os
import struct
import sys
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from archivist.services.image_inventory import ImageInventory, ImageWorkflowError, zip_times
from archivist.utils import timestamps
from archivist.utils.timestamps import FILETIME_EPOCH, FileTimes


def extra(tag, payload):
    return struct.pack("<HH", tag, len(payload)) + payload


def ntfs_dates(dates):
    ticks = lambda value: value // 100 + FILETIME_EPOCH if value is not None else 0
    return extra(0x000A, b"\0" * 4 + struct.pack(
        "<HHQQQ", 1, 24, ticks(dates.modified_ns), ticks(dates.accessed_ns), ticks(dates.created_ns),
    ))


def archive_bytes(local, central=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("picture.jpg", (2020, 1, 2, 3, 4, 6))
        info.extra = local
        archive.writestr(info, b"photo")
        if central is not None:
            info.extra = central
    return stream.getvalue()


def read_archive_dates(payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        position = archive.fp.tell()
        result = zip_times(archive, archive.infolist()[0])
        assert archive.fp.tell() == position
        return result


def test_exact_native_filesystem_dates(tmp_path):
    source = tmp_path / "original.jpg"
    source.write_bytes(b"photo")
    created = 1_234_567_800_987_654_300 if os.name == "nt" or sys.platform == "darwin" else None
    dates = FileTimes(1_400_000_000_123_456_700, created, 1_500_000_000_123_456_700)
    dates.restore(source)
    assert FileTimes.read(source) == dates
    destination = tmp_path / "copy.jpg"
    destination.write_bytes(source.read_bytes())
    dates.restore(destination)
    assert FileTimes.read(destination) == dates


def test_unknown_creation_is_not_inferred_or_restored(tmp_path, monkeypatch):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo")
    current = FileTimes.read(path)
    setter = Mock(side_effect=AssertionError("Must not set an unknown creation date"))
    monkeypatch.setattr(timestamps, "_windows_creation_time", setter)
    monkeypatch.setattr(timestamps, "_mac_creation_time", setter)
    FileTimes(1_000_000_000_000_000_000).restore(path)
    assert path.stat().st_mtime_ns == 1_000_000_000_000_000_000
    assert path.stat().st_atime_ns == current.accessed_ns
    setter.assert_not_called()


def test_unavailable_creation_setter_fails_explicitly(tmp_path, monkeypatch):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo")
    monkeypatch.setattr(timestamps, "os", SimpleNamespace(
        name="posix", utime=os.utime,
    ))
    monkeypatch.setattr(timestamps, "sys", SimpleNamespace(platform="linux"))
    with pytest.raises(OSError, match="cannot restore a known creation time"):
        FileTimes(1_000_000_000_000_000_000, 1_000_000_000_000_000_000).restore(path)
    assert path.exists()


def test_precision_loss_is_not_silent_success(tmp_path, monkeypatch):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo")
    actual_utime = os.utime

    def truncate(path, *, ns):
        actual_utime(path, ns=(ns[0], ns[1] // 1_000_000_000 * 1_000_000_000))

    monkeypatch.setattr(timestamps.os, "utime", truncate)
    with pytest.raises(OSError, match="modification-time precision"):
        FileTimes(1_000_000_000_123_456_700).restore(path)


def test_creation_verification_detects_ignored_setter(tmp_path, monkeypatch):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo")
    monkeypatch.setattr(timestamps, "os", SimpleNamespace(name="nt", utime=os.utime))
    monkeypatch.setattr(timestamps, "_windows_creation_time", lambda *args: None)
    monkeypatch.setattr(timestamps, "_creation_ns", lambda *args: 900)
    with pytest.raises(OSError, match="did not preserve the original creation time"):
        FileTimes(1_000_000_000_000_000_000, 800).restore(path)


def test_macos_attribute_abi_read_write_and_errors(tmp_path, monkeypatch):
    created = 1_100_000_000_123_456_789
    path = tmp_path / "photo.jpg"

    def get_date(name, attributes, buffer, size, flags):
        assert name == os.fsencode(path) and size == 20 and flags == 1
        assert ctypes.string_at(attributes, 24) == struct.pack("=HHIIIII", 5, 0, 0x200, 0, 0, 0, 0)
        buffer.raw = struct.pack("=Iqq", 20, *divmod(created, 1_000_000_000))
        return 0

    def set_date(name, attributes, buffer, size, flags):
        assert size == 16 and flags == 1
        assert buffer.raw == struct.pack("=qq", *divmod(created, 1_000_000_000))
        return 0

    library = SimpleNamespace(getattrlist=Mock(side_effect=get_date), setattrlist=Mock(side_effect=set_date))
    monkeypatch.setattr(timestamps.ctypes, "CDLL", lambda *args, **kwargs: library)
    assert timestamps._mac_creation_time(path) == created
    assert timestamps._mac_creation_time(path, created) == created
    library.getattrlist.side_effect = lambda name, attributes, buffer, size, flags: 0
    with pytest.raises(OSError, match="Invalid creation-time"):
        timestamps._mac_creation_time(path)
    library.setattrlist.side_effect = lambda *args: -1
    ctypes.set_errno(errno.ENOTSUP)
    with pytest.raises(OSError) as failure:
        timestamps._mac_creation_time(path, created)
    assert failure.value.errno == errno.ENOTSUP


@pytest.mark.skipif(os.name != "nt", reason="Windows native FILETIME error adapter")
def test_windows_setter_errors_close_handles(tmp_path, monkeypatch):
    kernel = SimpleNamespace(
        CreateFileW=Mock(return_value=ctypes.c_void_p(-1).value),
        SetFileTime=Mock(return_value=0), CloseHandle=Mock(return_value=1),
    )
    monkeypatch.setattr(timestamps.ctypes, "WinDLL", lambda *args, **kwargs: kernel)
    ctypes.set_last_error(5)
    with pytest.raises(OSError):
        timestamps._windows_creation_time(tmp_path / "a.jpg", 1_000_000_000)
    kernel.CloseHandle.assert_not_called()
    kernel.CreateFileW.return_value = 123
    with pytest.raises(OSError):
        timestamps._windows_creation_time(tmp_path / "a.jpg", 1_000_000_000)
    kernel.CloseHandle.assert_called_once_with(123)
    with pytest.raises(OSError, match="cannot be represented"):
        timestamps._windows_creation_time(tmp_path / "a.jpg", 123)


def test_ntfs_precision_overrides_unix_seconds_independent_of_order():
    dates = FileTimes(1_400_000_000_123_456_700, 1_200_000_000_987_654_300, 1_500_000_000_000_000_100)
    unix = extra(0x5455, struct.pack("<Biii", 7, 1_400_000_000, 1_500_000_000, 1_200_000_000))
    for fields in (ntfs_dates(dates) + unix, unix + ntfs_dates(dates)):
        assert read_archive_dates(archive_bytes(fields)) == dates


def test_local_only_unix_creation_and_access_with_central_flags():
    local = extra(0x5455, struct.pack("<Biii", 7, 1_400_000_000, 1_500_000_000, 1_200_000_000))
    central = extra(0x5455, struct.pack("<Bi", 7, 1_400_000_000))
    assert read_archive_dates(archive_bytes(local, central)) == FileTimes(
        1_400_000_000_000_000_000, 1_200_000_000_000_000_000, 1_500_000_000_000_000_000,
    )


def test_creation_only_unix_field_and_signed_pre_epoch_time():
    local = extra(0x5455, struct.pack("<Bi", 4, -123))
    central = extra(0x5455, b"\x04")
    dates = read_archive_dates(archive_bytes(local, central))
    assert dates.created_ns == -123_000_000_000 and dates.accessed_ns is None
    assert read_archive_dates(archive_bytes(extra(0x5455, struct.pack("<Bi", 1, -1)))).modified_ns == -1_000_000_000


def test_dos_metadata_does_not_invent_creation_or_access():
    dates = read_archive_dates(archive_bytes(b""))
    assert dates.created_ns is None and dates.accessed_ns is None
    assert dates.modified_ns % 1_000_000_000 == 0


@pytest.mark.parametrize("local,central", [
    (extra(0x5455, b"\x07\0"), b""),
    (extra(0x000A, b"\0" * 4 + struct.pack("<HH", 1, 24)), b""),
    (extra(0x5455, struct.pack("<Bi", 1, 123)), extra(0x5455, struct.pack("<Bi", 1, 124))),
])
def test_bad_or_conflicting_timestamp_metadata_blocks_inventory(tmp_path, local, central):
    (tmp_path / "bad.zip").write_bytes(archive_bytes(local, central))
    inventory = ImageInventory().scan(tmp_path)
    assert inventory.problems and not inventory.items


def test_invalid_local_header_is_rejected():
    payload = bytearray(archive_bytes(b""))
    payload[0] = 0
    with pytest.raises(ImageWorkflowError, match="Invalid ZIP local header"):
        read_archive_dates(payload)
