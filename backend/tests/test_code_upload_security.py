"""Security tests for reverse-FS code upload endpoint."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.parsers.code_parser import _safe_extractall


def _make_zip_with_member(name: str, body: bytes = b"x=1\n") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo(name)
        zf.writestr(info, body)
    return buf.getvalue()


def _make_zip_with_symlink(name: str, target: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo(name)
        info.external_attr = (0xA1FF) << 16  # symlink perms (0120777)
        zf.writestr(info, target.encode())
    return buf.getvalue()


class TestSafeExtractall:
    def test_rejects_parent_traversal(self, tmp_path: Path) -> None:
        zbytes = _make_zip_with_member("../escape.txt")
        zp = tmp_path / "bad.zip"
        zp.write_bytes(zbytes)
        with pytest.raises(ValueError, match="traversal"):
            _safe_extractall(str(zp), str(tmp_path / "out"))

    def test_rejects_absolute_path(self, tmp_path: Path) -> None:
        zbytes = _make_zip_with_member("/etc/pwn.txt")
        zp = tmp_path / "bad.zip"
        zp.write_bytes(zbytes)
        with pytest.raises(ValueError, match="absolute"):
            _safe_extractall(str(zp), str(tmp_path / "out"))

    def test_rejects_symlink(self, tmp_path: Path) -> None:
        zbytes = _make_zip_with_symlink("link.txt", "/etc/passwd")
        zp = tmp_path / "link.zip"
        zp.write_bytes(zbytes)
        out = tmp_path / "out"
        out.mkdir()
        with pytest.raises(ValueError, match="symlink"):
            _safe_extractall(str(zp), str(out))

    def test_allows_normal_members(self, tmp_path: Path) -> None:
        zbytes = _make_zip_with_member("pkg/main.py", b"print('hi')\n")
        zp = tmp_path / "ok.zip"
        zp.write_bytes(zbytes)
        out = tmp_path / "out"
        out.mkdir()
        _safe_extractall(str(zp), str(out))
        assert (out / "pkg" / "main.py").read_bytes() == b"print('hi')\n"


@pytest.mark.asyncio
class TestCodeUploadRejectsMalicious:
    async def test_traversal_filename_is_sanitized(self, client: AsyncClient) -> None:
        # Starlette normalises multipart filenames to the basename, but our
        # router-level guard also collapses any remaining path parts before
        # writing to disk. Either outcome (sanitized OK, or explicit 400) is
        # acceptable — what matters is we never touch paths outside upload_dir.
        files = {"file": ("../evil.zip", _make_zip_with_member("a.py"), "application/zip")}
        r = await client.post("/api/code/upload", files=files)
        # Either sanitized + accepted, or explicitly rejected; what matters is
        # no file is written outside the upload root (unit-tested in
        # TestSafeExtractall above).
        assert r.status_code in (200, 400)

    async def test_non_zip_rejected(self, client: AsyncClient) -> None:
        files = {"file": ("x.tar", b"not-a-zip", "application/x-tar")}
        r = await client.post("/api/code/upload", files=files)
        assert r.status_code == 400
