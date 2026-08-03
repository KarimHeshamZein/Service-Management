"""Proof-photo validation and storage.

Three gates before a byte is written to disk: the declared extension, the file's
own magic bytes, and a full decode by Pillow. Stored names are freshly generated
UUIDs, so a hostile original filename can never influence the path.
"""
from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .config import ALLOWED_EXTENSIONS, ALLOWED_IMAGE_TYPES, THUMBNAIL_MAX_EDGE, settings

STORAGE_KEY_RE = re.compile(r"^\d{4}/\d{2}/[0-9a-f]{32}(_thumb)?\.(jpg|png|webp)$")

_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)

_PIL_FORMAT_TO_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class UploadError(ValueError):
    """Raised with a message that is safe to show the user."""


@dataclass(slots=True)
class StoredImage:
    storage_key: str
    thumbnail_key: str | None
    original_filename: str
    content_type: str
    file_size: int


def _sniff(data: bytes) -> str | None:
    for signature, mime in _MAGIC:
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _clean_filename(name: str) -> str:
    """Keep the original name for display only; strip anything path-like."""
    name = (name or "upload").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip() or "upload"
    return name[:120]


def validate_image(filename: str, data: bytes) -> tuple[str, str]:
    """Return (content_type, canonical_extension) or raise UploadError."""
    display_name = _clean_filename(filename)

    if not data:
        raise UploadError(f"“{display_name}” is empty.")

    if len(data) > settings.max_upload_bytes:
        raise UploadError(
            f"“{display_name}” is {len(data) / 1024 / 1024:.1f} MB. "
            f"The limit is {settings.max_upload_mb:g} MB per photo."
        )

    extension = Path(display_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadError(f"“{display_name}” is not a JPEG, PNG or WebP file.")

    sniffed = _sniff(data)
    if sniffed is None or sniffed not in ALLOWED_IMAGE_TYPES:
        raise UploadError(f"“{display_name}” is not a real image file.")

    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as probe:
            probe.load()
            pil_format = probe.format or ""
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UploadError(f"“{display_name}” could not be read as an image.") from exc

    decoded_mime = _PIL_FORMAT_TO_MIME.get(pil_format.upper())
    if decoded_mime != sniffed:
        raise UploadError(f"“{display_name}” has contents that do not match its file type.")

    return sniffed, ALLOWED_IMAGE_TYPES[sniffed]


def store_image(filename: str, data: bytes) -> StoredImage:
    content_type, extension = validate_image(filename, data)

    now = datetime.now(timezone.utc)
    folder = f"{now:%Y}/{now:%m}"
    stem = uuid.uuid4().hex
    storage_key = f"{folder}/{stem}{extension}"

    target_dir = settings.upload_dir / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / storage_key).write_bytes(data)

    thumbnail_key: str | None = None
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE))
            thumbnail_key = f"{folder}/{stem}_thumb.jpg"
            img.save(settings.upload_dir / thumbnail_key, format="JPEG", quality=82)
    except (OSError, ValueError):
        thumbnail_key = None  # Serving falls back to the original.

    return StoredImage(
        storage_key=storage_key,
        thumbnail_key=thumbnail_key,
        original_filename=_clean_filename(filename),
        content_type=content_type,
        file_size=len(data),
    )


def resolve_storage_path(storage_key: str) -> Path:
    """Map a stored key to a path, refusing anything that escapes the upload root."""
    if not STORAGE_KEY_RE.match(storage_key or ""):
        raise UploadError("Invalid storage key")

    root = settings.upload_dir.resolve()
    candidate = (root / storage_key).resolve()
    if root != candidate and root not in candidate.parents:
        raise UploadError("Invalid storage key")
    if not candidate.is_file():
        raise UploadError("File not found")
    return candidate


def delete_stored(*keys: str | None) -> None:
    """Best-effort cleanup used when a submission fails after files were written."""
    for key in keys:
        if not key:
            continue
        try:
            resolve_storage_path(key).unlink(missing_ok=True)
        except UploadError:
            continue
