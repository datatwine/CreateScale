import os
import tempfile
from io import BytesIO
from PIL import Image
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from users.models import Profile, Upload


def _valid_image():
    """Minimal 1x1 red JPEG that PIL can actually open."""
    img = Image.new("RGB", (1, 1), color="red")
    buf = BytesIO()
    img.save(buf, "JPEG")
    buf.seek(0)
    return SimpleUploadedFile("test.jpg", buf.getvalue(), content_type="image/jpeg")


def _video_file():
    return SimpleUploadedFile("test.mp4", b"fake-video-content", content_type="video/mp4")


_TEMP_MEDIA = tempfile.mkdtemp()

_CACHE_LOCMEM = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@override_settings(
    MEDIA_ROOT=_TEMP_MEDIA,
    CACHES=_CACHE_LOCMEM,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    CELERY_BROKER_URL="memory://",
)
class UploadAPIIntegrationTest(TestCase):
    """API /api/users/me/uploads/ — mutual exclusion of image & video."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("uploader", password="Pass123!")
        self.profile = Profile.objects.get(user=self.user)
        self.token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

    def tearDown(self):
        Upload.objects.all().delete()

    def test_api_accepts_image_only(self):
        resp = self.client.post("/api/users/me/uploads/", {
            "image": _valid_image(),
            "caption": "Great photo",
        }, format="multipart")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Upload.objects.count(), 1)
        u = Upload.objects.first()
        self.assertTrue(u.image)
        self.assertFalse(u.video)

    def test_api_accepts_video_only(self):
        resp = self.client.post("/api/users/me/uploads/", {
            "video": _video_file(),
            "caption": "Nice clip",
        }, format="multipart")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Upload.objects.count(), 1)
        u = Upload.objects.first()
        self.assertTrue(u.video)
        self.assertFalse(u.image)

    def test_api_rejects_both_image_and_video(self):
        resp = self.client.post("/api/users/me/uploads/", {
            "image": _valid_image(),
            "video": _video_file(),
            "caption": "Both files",
        }, format="multipart")
        self.assertEqual(resp.status_code, 400)
        errs = str(resp.data).lower()
        self.assertIn("only one file", errs)
        self.assertEqual(Upload.objects.count(), 0)

    def test_api_rejects_neither(self):
        resp = self.client.post("/api/users/me/uploads/", {
            "caption": "No media",
        }, format="multipart")
        self.assertEqual(resp.status_code, 400)
        errs = str(resp.data).lower()
        self.assertIn("requires an image", errs)
        self.assertEqual(Upload.objects.count(), 0)
