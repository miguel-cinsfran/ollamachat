"""Media helpers — wx-free, testable in WSL.

Extracts images from ZIP files and keyframes from video via ffmpeg.
All functions return a list of (base64_str, mime_type) tuples or an error
tuple: ([], error_message). Never raise.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "bmp", "gif", "webp"})
_MIME_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "bmp": "image/bmp",
    "gif": "image/gif",
    "webp": "image/webp",
}

MAX_IMAGES = 20


def _encode(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower().lstrip(".")
    mime = _MIME_MAP.get(ext, "image/jpeg")
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return b64, mime


def images_from_folder(folder_path: str) -> tuple[list[tuple[str, str]], Optional[str]]:
    """Collect images from a folder (non-recursive, sorted, up to MAX_IMAGES).

    Returns (images, error). images is a list of (base64, mime) tuples.
    error is None on success, an error message on failure.
    """
    try:
        folder = Path(folder_path)
        entries = sorted(
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower().lstrip(".") in IMAGE_EXTENSIONS
        )
        if not entries:
            return [], "No se encontraron imágenes en la carpeta."
        entries = entries[:MAX_IMAGES]
        return [_encode(f) for f in entries], None
    except Exception as e:
        return [], str(e)


def images_from_zip(zip_path: str) -> tuple[list[tuple[str, str]], Optional[str]]:
    """Extract images from a ZIP archive and encode them.

    Decompresses to a temporary directory, collects images, cleans up.
    Returns (images, error).
    """
    tmp_dir: Optional[str] = None
    try:
        if not zipfile.is_zipfile(zip_path):
            return [], f"No es un archivo ZIP válido: {zip_path}"
        tmp_dir = tempfile.mkdtemp(prefix="bellbird_zip_")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)
        images: list[tuple[str, str]] = []
        for f in sorted(Path(tmp_dir).rglob("*")):
            if f.is_file() and f.suffix.lower().lstrip(".") in IMAGE_EXTENSIONS:
                images.append(_encode(f))
                if len(images) >= MAX_IMAGES:
                    break
        if not images:
            return [], "El ZIP no contiene imágenes."
        return images, None
    except Exception as e:
        return [], str(e)
    finally:
        if tmp_dir:
            import shutil as _shutil
            try:
                _shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass


def keyframes_from_video(
    video_path: str, fps: float = 0.5
) -> tuple[list[tuple[str, str]], Optional[str]]:
    """Extract keyframes from a video file using ffmpeg.

    Returns (images, error). If ffmpeg is not installed, returns ([], error_msg)
    without crashing. Cleans up temporary files.
    """
    if shutil.which("ffmpeg") is None:
        return [], (
            "ffmpeg no está instalado. Instalalo para describir videos. "
            "En Windows: winget install ffmpeg"
        )
    tmp_dir: Optional[str] = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="bellbird_vid_")
        out_pattern = str(Path(tmp_dir) / "frame_%04d.jpg")
        result = subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-vf", f"fps={fps}",
                "-frames:v", str(MAX_IMAGES),
                out_pattern,
            ],
            capture_output=True,
            timeout=60,
        )
        frames = sorted(Path(tmp_dir).glob("frame_*.jpg"))
        if not frames:
            stderr = result.stderr.decode("utf-8", errors="replace")[:500]
            return [], f"ffmpeg no extrajo frames. {stderr}"
        return [_encode(f) for f in frames[:MAX_IMAGES]], None
    except subprocess.TimeoutExpired:
        return [], "ffmpeg tardó demasiado (timeout 60s)."
    except Exception as e:
        return [], str(e)
    finally:
        if tmp_dir:
            import shutil as _shutil
            try:
                _shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
