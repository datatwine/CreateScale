import tempfile
from io import BytesIO

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from users.models import Upload

_TEMP_MEDIA = tempfile.mkdtemp()


@override_settings(
    MEDIA_ROOT=_TEMP_MEDIA,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    CELERY_BROKER_URL="memory://",
    CELERY_RESULT_BACKEND="cache+memory://",
)
class TestUploadWebIntegration(TestCase):
    """POST /users/profile/ with upload_submit — web upload lifecycle."""

    def setUp(self):
        self.user = User.objects.create_user("uploader", password="testpass")
        self.client.login(username="uploader", password="testpass")

    @staticmethod
    def _fake_image(name="test.jpg"):
        buf = BytesIO()
        Image.new("RGB", (80, 80), color="red").save(buf, format="JPEG")
        buf.seek(0)
        return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")

    @staticmethod
    def _fake_video(name="clip.mp4"):
        return SimpleUploadedFile(name, b"\x00" * 100, content_type="video/mp4")

    def test_upload_image_only(self):
        resp = self.client.post(
            "/users/profile/",
            {
                "upload_submit": "1",
                "caption": "My art",
                "image": self._fake_image(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Upload.objects.filter(profile__user=self.user).count(), 1)
        upload = Upload.objects.get(profile__user=self.user)
        self.assertEqual(upload.caption, "My art")
        self.assertTrue(upload.image)
        self.assertFalse(upload.video)

    def test_upload_video_only(self):
        resp = self.client.post(
            "/users/profile/",
            {
                "upload_submit": "1",
                "caption": "Great performance",
                "video": self._fake_video(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Upload.objects.filter(profile__user=self.user).count(), 1)
        upload = Upload.objects.get(profile__user=self.user)
        self.assertEqual(upload.caption, "Great performance")
        self.assertTrue(upload.video)
        self.assertFalse(upload.image)

    def test_upload_no_file(self):
        resp = self.client.post(
            "/users/profile/",
            {
                "upload_submit": "1",
                "caption": "No file attached",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "error", status_code=200)
        self.assertEqual(Upload.objects.count(), 0)

    def test_upload_both_image_and_video(self):
        resp = self.client.post(
            "/users/profile/",
            {
                "upload_submit": "1",
                "caption": "Both files",
                "image": self._fake_image(),
                "video": self._fake_video(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Upload.objects.filter(profile__user=self.user).count(), 1)
        upload = Upload.objects.get(profile__user=self.user)
        self.assertTrue(upload.image)
        self.assertTrue(upload.video)

    def test_image_too_large(self):
        large = SimpleUploadedFile(
            "large.jpg",
            b"\x00" * (5 * 1024 * 1024 + 1),
            content_type="image/jpeg",
        )
        resp = self.client.post(
            "/users/profile/",
            {
                "upload_submit": "1",
                "caption": "Large image",
                "image": large,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "error", status_code=200)
        self.assertEqual(Upload.objects.count(), 0)

    def test_video_too_large(self):
        large = SimpleUploadedFile(
            "large.mp4",
            b"\x00" * (120 * 1024 * 1024 + 1),
            content_type="video/mp4",
        )
        resp = self.client.post(
            "/users/profile/",
            {
                "upload_submit": "1",
                "caption": "Large video",
                "video": large,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "error", status_code=200)
        self.assertEqual(Upload.objects.count(), 0)

    def test_wrong_file_type(self):
        fake_img = SimpleUploadedFile(
            "fake.jpg",
            b"%PDF-1.4 fake pdf content",
            content_type="application/pdf",
        )
        resp = self.client.post(
            "/users/profile/",
            {
                "upload_submit": "1",
                "caption": "Fake image",
                "image": fake_img,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "error", status_code=200)
        self.assertEqual(Upload.objects.count(), 0)

    def test_upload_appears_on_profile_page(self):
        resp = self.client.post(
            "/users/profile/",
            {
                "upload_submit": "1",
                "caption": "Visible upload",
                "image": self._fake_image(),
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Visible upload")

    def test_anonymous_user_cannot_upload(self):
        self.client.logout()
        resp = self.client.post(
            "/users/profile/",
            {
                "upload_submit": "1",
                "caption": "Hacked",
                "image": self._fake_image(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)
        self.assertEqual(Upload.objects.count(), 0)
