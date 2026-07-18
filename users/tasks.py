"""
Celery tasks for the users app.

`compress_upload_video` re-encodes a stored Upload.video to ~1080p H.264 CRF 24
in the background. The user's upload completes immediately with the raw video;
the worker swaps in the compressed version ~10-30s later, transparently.

`process_uploaded_image` conditionally resizes/strips EXIF for presigned image
uploads > 2 MB. Files ≤ 2 MB are assumed client-compressed and skipped.

Non-regression contract: ON ANY FAILURE the raw file stays in R2 unchanged —
the Upload row is never broken; the file just stays at its original size.
"""

import os
import subprocess
import tempfile
import logging

from celery import shared_task
from django.core.files import File

log = logging.getLogger(__name__)


@shared_task(time_limit=300, soft_time_limit=280)
def compress_upload_video(upload_id):
    """Re-encode Upload.video to ~1080p H.264 ~4 Mbps + AAC 128k.

    R2 egress is free, so downloading the raw and re-uploading the compressed
    version costs only storage. The raw key is deleted once the compressed
    version is saved successfully.
    """
    # Local import to avoid circular import at module load
    from users.models import Upload

    try:
        upload = Upload.objects.get(pk=upload_id)
    except Upload.DoesNotExist:
        return
    if not upload.video:
        return

    src = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    dst = src.name.replace(".mp4", "_out.mp4")
    try:
        # 1) Pull the raw video down from storage (R2 egress is free)
        with upload.video.open("rb") as f:
            for chunk in f.chunks():
                src.write(chunk)
        src.close()

        # 2) Re-encode with ffmpeg. Fits inside 1920x1080 keeping aspect ratio.
        try:
            subprocess.run(
                [
                    "ffmpeg", "-i", src.name,
                    "-vf",
                    "scale=w=1920:h=1080:force_original_aspect_ratio=decrease:force_divisible_by=2",
                    "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",   # streaming-friendly
                    "-y", dst,
                ],
                check=True,
                capture_output=True,
                timeout=270,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            # ffmpeg blew up — leave the raw file in place; upload still works
            log.warning("ffmpeg failed for upload %s: %s", upload_id, e)
            return

        # 3) Swap the compressed file in. Pass only the basename — Django's
        #    upload_to='profile_videos' will prepend the directory itself, so
        #    passing the full path would double-prefix it.
        #    AWS_S3_FILE_OVERWRITE=False also means storage assigns a new
        #    unique suffix; we delete the raw original afterwards.
        old_name = upload.video.name
        basename = os.path.basename(old_name)
        with open(dst, "rb") as out:
            upload.video.save(basename, File(out), save=True)
        if upload.video.name != old_name:
            try:
                upload.video.storage.delete(old_name)
            except Exception as e:
                log.warning("Could not delete raw video %s: %s", old_name, e)

    finally:
        for p in (src.name, dst):
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass


@shared_task(time_limit=120, soft_time_limit=110)
def process_uploaded_image(upload_id):
    """Conditionally resize/strip EXIF on presigned uploads > 2 MB.

    - Files ≤ 2 MB: client already compressed (browser-image-compression / Expo
      ImageManipulator). Skip — saves a download + re-upload round trip.
    - Files > 2 MB: download from R2 → Pillow → re-upload.
    - On ANY failure: original file stays untouched in R2.
    """
    from users.models import Upload
    from users.utils.image import process_image

    try:
        upload = Upload.objects.get(pk=upload_id)
    except Upload.DoesNotExist:
        return "upload not found"

    if not upload.image:
        return "no image"

    # Check file size via storage backend (HEAD request, no download)
    try:
        size = upload.image.storage.size(upload.image.name)
    except Exception:
        return "size check failed — skipping"

    if size <= 2 * 1024 * 1024:  # 2 MB
        return f"skipped — {size} bytes (under 2 MB)"

    # Download, process, re-upload
    try:
        from io import BytesIO

        with upload.image.open("rb") as f:
            raw = BytesIO(f.read())
            raw.name = upload.image.name.split("/")[-1]

        processed = process_image(raw, "gallery")
        if processed is raw:
            return "pillow returned original unchanged"

        # Save processed file — overwrites the R2 key
        old_name = upload.image.name
        upload.image.save(old_name.split("/")[-1], processed, save=True)

        # Delete original if key changed (unlikely with same name pattern)
        if upload.image.name != old_name:
            try:
                upload.image.storage.delete(old_name)
            except Exception as e:
                log.warning("Could not delete original image %s: %s", old_name, e)

        return f"processed — {size} → {upload.image.size} bytes"

    except Exception as e:
        log.warning("process_uploaded_image(%s) failed: %s — original untouched", upload_id, e)
        return f"error: {e}"
