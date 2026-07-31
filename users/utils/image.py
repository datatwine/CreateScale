"""
Server-side image safety net.

Catches every upload path (web form, DRF API, Django admin, future clients) and:
  - applies camera rotation from EXIF then STRIPS all EXIF (removes GPS, etc.)
  - downscales the longest edge to a per-kind cap
  - re-encodes as WebP quality 60 (storage-optimized, visually equivalent on mobile)
  - is exception-safe: any PIL hiccup falls back to the original file untouched

Called from model save() hooks via `is_fresh_upload()` so it only fires for
brand-new UploadedFile instances — never for files already in storage.
"""

import logging
from io import BytesIO

from PIL import Image, ImageOps
from django.core.files.uploadedfile import InMemoryUploadedFile

_log = logging.getLogger(__name__)

# kind -> (max longest edge px, WebP quality)
IMAGE_PROFILES = {
    "avatar": (512, 60),  # Profile.profile_picture
    "cover": (1920, 60),  # Profile.cover_photo
    "gallery": (1080, 60),  # Upload.image
}


def is_fresh_upload(fieldfile) -> bool:
    """True only for a fresh upload that hasn't been saved to storage yet.

    Uses Django's internal `_committed` flag — set False by the ImageField
    descriptor when a new file is assigned, flipped True by storage.save().
    This is cheap (single attribute read, no I/O), unlike `.file` which
    would download the file from S3/R2 just to check its type.

    Guards the model save() hooks so re-saves (admin edits, Celery task
    swapping the video, etc.) don't double-compress an already-stored image.
    """
    return bool(fieldfile) and getattr(fieldfile, "_committed", True) is False


def process_image(uploaded_file, kind: str = "gallery"):
    """Resize + auto-rotate + strip EXIF + re-encode JPEG. ~50-150ms.

    Returns the ORIGINAL file unchanged on ANY failure (logs a warning).
    A failure here NEVER breaks the user's upload.
    """
    if kind not in IMAGE_PROFILES:
        kind = "gallery"
    max_edge, quality = IMAGE_PROFILES[kind]

    try:
        img = Image.open(uploaded_file)
        # Apply camera rotation, then EXIF is dropped (the re-encoded file has none)
        img = ImageOps.exif_transpose(img)
        # JPEG has no alpha; convert palette/RGBA to plain RGB
        if img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGBA")
        # Resize only if larger than the per-kind cap, preserving aspect
        w, h = img.size
        if max(w, h) > max_edge:
            scale = max_edge / max(w, h)
            img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="WEBP", quality=quality)
        buf.seek(0)
        name = uploaded_file.name.rsplit(".", 1)[0] + ".webp"
        return InMemoryUploadedFile(
            file=buf,
            field_name="ImageField",
            name=name,
            content_type="image/webp",
            size=buf.getbuffer().nbytes,
            charset=None,
        )
    except Exception as e:
        _log.warning(
            "process_image(%s) failed: %s — saving original untouched", kind, e
        )
        try:
            uploaded_file.seek(0)  # reset pointer so Django can still read the original
        except Exception:
            pass
        return uploaded_file
