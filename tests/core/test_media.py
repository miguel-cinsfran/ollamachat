"""Tests for bellbird.core.media — images_from_folder, images_from_zip, keyframes_from_video."""

import base64
import io
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bellbird.core.media import (
    MAX_IMAGES,
    images_from_folder,
    images_from_zip,
    keyframes_from_video,
)


def _make_tiny_png(path: Path) -> None:
    """Write a minimal 1×1 PNG file."""
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    path.write_bytes(png_bytes)


class TestImagesFromFolder:
    def test_returns_images_from_folder(self, tmp_path):
        for name in ("a.png", "b.png"):
            _make_tiny_png(tmp_path / name)
        images, err = images_from_folder(str(tmp_path))
        assert err is None
        assert len(images) == 2
        for b64, mime in images:
            assert mime.startswith("image/")
            base64.b64decode(b64)  # valid base64

    def test_ignores_non_image_files(self, tmp_path):
        _make_tiny_png(tmp_path / "ok.png")
        (tmp_path / "skip.txt").write_text("text")
        images, err = images_from_folder(str(tmp_path))
        assert len(images) == 1

    def test_empty_folder_returns_error(self, tmp_path):
        images, err = images_from_folder(str(tmp_path))
        assert images == []
        assert err

    def test_missing_folder_returns_error(self):
        images, err = images_from_folder("/nonexistent/path/xyz")
        assert images == []
        assert err

    def test_caps_at_max_images(self, tmp_path):
        for i in range(MAX_IMAGES + 3):
            _make_tiny_png(tmp_path / f"img_{i:03d}.png")
        images, err = images_from_folder(str(tmp_path))
        assert err is None
        assert len(images) == MAX_IMAGES


class TestImagesFromZip:
    def _make_zip(self, path: Path, image_names: list[str]) -> None:
        with zipfile.ZipFile(path, "w") as zf:
            for name in image_names:
                buf = io.BytesIO()
                _make_tiny_png(path.parent / "_tmp.png")
                zf.write(path.parent / "_tmp.png", name)

    def test_extracts_images_from_zip(self, tmp_path):
        zip_path = tmp_path / "imgs.zip"
        img_path = tmp_path / "img.png"
        _make_tiny_png(img_path)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(img_path, "photo.png")
        images, err = images_from_zip(str(zip_path))
        assert err is None
        assert len(images) == 1

    def test_invalid_zip_returns_error(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not a zip")
        images, err = images_from_zip(str(bad))
        assert images == []
        assert err

    def test_empty_zip_returns_error(self, tmp_path):
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w"):
            pass
        images, err = images_from_zip(str(zip_path))
        assert images == []
        assert err

    def test_cleanup_after_success(self, tmp_path):
        import tempfile
        original_mkdtemp = tempfile.mkdtemp
        created_dirs = []
        def track_mkdtemp(**kwargs):
            d = original_mkdtemp(**kwargs)
            created_dirs.append(d)
            return d
        zip_path = tmp_path / "test.zip"
        img_path = tmp_path / "img.png"
        _make_tiny_png(img_path)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(img_path, "img.png")
        with patch("tempfile.mkdtemp", side_effect=track_mkdtemp):
            images_from_zip(str(zip_path))
        for d in created_dirs:
            assert not Path(d).exists(), f"Temp dir not cleaned up: {d}"


class TestKeyframesFromVideo:
    def test_no_ffmpeg_returns_error(self):
        with patch("shutil.which", return_value=None):
            images, err = keyframes_from_video("/fake/video.mp4")
        assert images == []
        assert "ffmpeg" in err.lower()

    def test_ffmpeg_missing_raises_gracefully(self):
        images, err = keyframes_from_video("/nonexistent/path/video.mp4")
        assert isinstance(images, list)
        assert isinstance(err, (str, type(None)))
