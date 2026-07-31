import tempfile
from io import BytesIO

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from users.models import Profile

_TEMP_MEDIA = tempfile.mkdtemp()


@override_settings(
    MEDIA_ROOT=_TEMP_MEDIA,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    CELERY_BROKER_URL="memory://",
    CELERY_RESULT_BACKEND="cache+memory://",
)
class TestProfileWebIntegration(TestCase):
    """POST /users/profile/ with profile_submit — profile update lifecycle."""

    def setUp(self):
        self.user = User.objects.create_user("rahul", password="testpass")
        self.profile = Profile.objects.get(user=self.user)
        self.profile.bio = "Original bio"
        self.profile.profession = "Photographer"
        self.profile.location = "Mumbai"
        self.profile.save()
        self.client.login(username="rahul", password="testpass")

    @staticmethod
    def _fake_image(name="test.jpg"):
        buf = BytesIO()
        Image.new("RGB", (80, 80), color="blue").save(buf, format="JPEG")
        buf.seek(0)
        return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")

    def _base_payload(self):
        return {
            "profile_submit": "1",
            "bio": self.profile.bio,
            "profession": self.profile.profession,
            "location": self.profile.location,
        }

    def test_update_bio_only(self):
        resp = self.client.post(
            "/users/profile/",
            {
                **self._base_payload(),
                "bio": "Wildlife photographer based in Pune",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, "Wildlife photographer based in Pune")
        self.assertEqual(self.profile.profession, "Photographer")

    def test_update_multiple_fields(self):
        resp = self.client.post(
            "/users/profile/",
            {
                **self._base_payload(),
                "bio": "Portrait & wedding photographer",
                "profession": "Photographer & Editor",
                "location": "Delhi",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, "Portrait & wedding photographer")
        self.assertEqual(self.profile.profession, "Photographer & Editor")
        self.assertEqual(self.profile.location, "Delhi")

    def test_profile_picture_upload(self):
        resp = self.client.post(
            "/users/profile/",
            {
                **self._base_payload(),
                "profile_picture": self._fake_image(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.profile_picture)

    def test_cover_photo_upload(self):
        resp = self.client.post(
            "/users/profile/",
            {
                **self._base_payload(),
                "cover_photo": self._fake_image(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.cover_photo)

    def test_toggle_is_performer(self):
        resp = self.client.post(
            "/users/profile/",
            {
                **self._base_payload(),
                "is_performer": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_performer)

        resp = self.client.post(
            "/users/profile/",
            {
                **self._base_payload(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_performer)

    def test_toggle_is_potential_client(self):
        resp = self.client.post(
            "/users/profile/",
            {
                **self._base_payload(),
                "is_potential_client": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_potential_client)

        resp = self.client.post(
            "/users/profile/",
            {
                **self._base_payload(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_potential_client)

    def test_missing_field_wiped_to_blank(self):
        payload = self._base_payload()
        del payload["profession"]
        resp = self.client.post("/users/profile/", payload)
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profession, "")

    def test_updated_data_appears_on_page(self):
        resp = self.client.post(
            "/users/profile/",
            {
                **self._base_payload(),
                "bio": "New bio visible on page",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "New bio visible on page")

    def test_anonymous_user_redirected(self):
        self.client.logout()
        resp = self.client.get("/users/profile/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)
