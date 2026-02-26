from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Profile, Upload
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile


# Create your tests here.
class SignupViewTest(TestCase):
    def test_signup_valid_user(self):
        # Test that a user can successfully sign up with valid credentials
        response = self.client.post(reverse('signup'), {  # Send a POST request to the signup URL
            'username': 'testuser',                     # Provide a valid username
            'email': 'testuser@example.com',            # Provide a valid email
            'password1': 'strongpassword123',           # Provide a strong password
            'password2': 'strongpassword123',           # Confirm the password
            'profession': 'Engineer',                  # Specify a profession
            'location': 'New York'                     # Specify a location
        })
        self.assertEqual(response.status_code, 302)     # Expect a redirect on successful signup
        self.assertTrue(User.objects.filter(username='testuser').exists())  # Check that the user is created
        user = User.objects.get(username='testuser')   # Fetch the newly created user
        self.assertEqual(user.profile.profession, 'Engineer')  # Verify the profession was saved in the profile
        self.assertEqual(user.profile.location, 'New York')    # Verify the location was saved in the profile

    def test_signup_invalid_user_missing_fields(self):
        # Test that signup fails if required fields are missing
        response = self.client.post(reverse('signup'), {  # Send a POST request with incomplete data
            'username': 'testuser',                     # Provide only the username
            'password1': 'strongpassword123',           # Provide the password
            'password2': 'strongpassword123'            # Confirm the password
            # Missing email, profession, and location
        })
        self.assertEqual(response.status_code, 200)     # Expect the form to be re-rendered due to validation failure
        self.assertFalse(User.objects.filter(username='testuser').exists())  # Ensure the user is not created



class ProfileViewTest(TestCase):
    def setUp(self):
        # Set up a test user and log them in
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.login(username='testuser', password='password123')  # Simulate a logged-in user
        self.profile = Profile.objects.get(user=self.user)  # Fetch the associated profile

    def test_profile_access(self):
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        # Check if the upload form by checking the presence of an input field with id 'id_image'
        self.assertContains(response, '<input', status_code=200)
        self.assertContains(response, 'id="id_image"', status_code=200)

    def test_profile_update(self):
        # Test updating profile fields (bio, profession, location)
        response = self.client.post(reverse('profile'), {
            'bio': 'Updated bio',
            'profession': 'Doctor',
            'location': 'San Francisco'
        })
        self.assertEqual(response.status_code, 200)  # Expect 200 since there's no redirect
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, 'Updated bio')
        self.assertEqual(self.profile.profession, 'Doctor')
        self.assertEqual(self.profile.location, 'San Francisco')


    def test_upload_image(self):
        """
        Test uploading a valid in-memory image to the profile page.
        """
        image = generate_test_image()  # Use a valid image generator

        # Submit a POST request with a valid image
        response = self.client.post(reverse('profile'), {
            'caption': 'Test image upload',
            'image': image
        })

        # Debug response if status code is 200
        if response.status_code == 200:
            print("Form validation failed. Errors:")
            print(response.content.decode())

        # Expect a 200 response and ensure the image is saved
        self.assertEqual(response.status_code, 200, "Form should re-render after image upload.")
        self.assertTrue(
            Upload.objects.filter(profile=self.profile, caption='Test image upload').exists(),
            "The image should be saved and linked to the user's profile"
        )


    def test_upload_image_displayed(self):
        """
        Test uploading an image and verify it is displayed dynamically on the profile page.
        """
        image = generate_test_image()  # Generate a valid in-memory image
        self.client.post(reverse('profile'), {
            'caption': 'Test image upload',
            'image': image
        })

        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)

        # Adjust the regex to match any dynamically generated image file in the media directory
        self.assertRegex(
            response.content.decode(),
            r'<img src="/media/.*\.jpg"',
            "Uploaded image should be displayed dynamically on the profile page."
        )





def generate_test_image():
        """
        Generate an in-memory test image that Django recognizes as valid.
        """
        image = Image.new('RGB', (100, 100), color='blue')  # Create a simple image
        buffer = BytesIO()
        image.save(buffer, format='JPEG')  # Save as JPEG
        buffer.seek(0)
        return InMemoryUploadedFile(
        buffer, 'image', 'test.jpg', 'image/jpeg', buffer.tell(), None
        )


from django.test import TestCase

from django.test import TestCase


def generate_test_image():
    """
    Generate an in-memory test image for profile pictures.
    """
    image = Image.new('RGB', (100, 100), color='blue')  # Create a simple image
    buffer = BytesIO()
    image.save(buffer, format='JPEG')  # Save as JPEG
    buffer.seek(0)
    return InMemoryUploadedFile(
        buffer, None, 'test.jpg', 'image/jpeg', buffer.tell(), None
    )


class GlobalFeedViewTest(TestCase):
    def setUp(self):
        # Create test user and log them in
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.login(username='testuser', password='password123')

        # Create other users and their profiles with profile pictures
        self.other_user1 = User.objects.create_user(username='user1', password='password123')
        self.other_user2 = User.objects.create_user(username='user2', password='password123')

        self.other_user1.profile.profession = 'Engineer'
        self.other_user1.profile.profile_picture = generate_test_image()  # Add profile picture
        self.other_user1.profile.save()

        self.other_user2.profile.profession = 'Doctor'
        self.other_user2.profile.profile_picture = generate_test_image()  # Add profile picture
        self.other_user2.profile.save()

    def test_global_feed_access(self):
        """
        Test that the global feed page is accessible for logged-in users.
        """
        response = self.client.get(reverse('global-feed'))  # Access the global feed URL
        self.assertEqual(response.status_code, 200)  # Confirm the page loads successfully
        self.assertTemplateUsed(response, 'users/global_feed.html')  # Confirm correct template usage

    def test_profiles_displayed(self):
        """
        Test that all profiles except the logged-in user's profile are displayed.
        """
        response = self.client.get(reverse('global-feed'))  # Access the global feed
        self.assertContains(response, 'user1', msg_prefix="User1's profile should be displayed.")
        self.assertContains(response, 'user2', msg_prefix="User2's profile should be displayed.")
        self.assertNotContains(response, 'testuser', msg_prefix="Logged-in user's profile should not be displayed.")

    def test_profession_filter(self):
        """
        Test filtering of profiles by profession in the global feed.
        """
        response = self.client.get(reverse('global-feed') + '?professions=Engineer')
        self.assertContains(response, 'user1', msg_prefix="User1 (Engineer) should be displayed with filter.")
        self.assertNotContains(response, 'user2', msg_prefix="User2 (Doctor) should not be displayed with 'Engineer' filter.")

    def test_empty_profession_filter(self):
        """
        Test that all profiles are displayed if no profession filter is applied.
        """
        response = self.client.get(reverse('global-feed'))  # No filtering parameters
        self.assertContains(response, 'user1', msg_prefix="User1 should be displayed without a filter.")
        self.assertContains(response, 'user2', msg_prefix="User2 should be displayed without a filter.")


from django.test import TestCase

def generate_test_image():
    """
    Generate an in-memory test image for uploads or profile pictures.
    """
    image = Image.new('RGB', (100, 100), color='blue')  # Create a simple image
    buffer = BytesIO()
    image.save(buffer, format='JPEG')  # Save as JPEG
    buffer.seek(0)
    return InMemoryUploadedFile(
        buffer, None, 'test.jpg', 'image/jpeg', buffer.tell(), None
    )

class ProfileDetailViewTest(TestCase):
    def setUp(self):
        # Create test user and their profile
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.user.profile.bio = "Test bio for testuser."
        self.user.profile.profile_picture = generate_test_image()  # Assign a profile picture
        self.user.profile.save()

        # Create test uploads for the user
        self.upload1 = Upload.objects.create(
            profile=self.user.profile,
            image=generate_test_image(),
            caption="Test upload 1"
        )
        self.upload2 = Upload.objects.create(
            profile=self.user.profile,
            image=generate_test_image(),
            caption="Test upload 2"
        )

        # Log in the test user
        self.client.login(username='testuser', password='password123')

    def test_profile_detail_access(self):
        """
        Test that the profile detail page is accessible.
        """
        response = self.client.get(reverse('profile-detail', args=[self.user.id]))
        self.assertEqual(response.status_code, 200)  # Ensure the page loads successfully
        self.assertTemplateUsed(response, 'users/profile_detail.html')  # Confirm the correct template is used

    def test_profile_data_display(self):
        """
        Test that the correct profile data is displayed on the profile detail page.
        """
        # Debug: Verify the bio is saved in the database
        self.assertEqual(self.user.profile.bio, "Test bio for testuser.", "Bio should be saved correctly in the database.")

        # Access the profile detail page
        response = self.client.get(reverse('profile-detail', args=[self.user.id]))

        # Check for username and bio in the rendered template
        self.assertContains(response, "testuser", msg_prefix="Username should be displayed.")
        self.assertContains(response, "Test bio for testuser.", msg_prefix="Bio should be displayed.")


    def test_profile_picture_display(self):
        """
        Test that the profile picture is displayed on the profile detail page.
        """
        response = self.client.get(reverse('profile-detail', args=[self.user.id]))
        self.assertContains(
            response,
            'src="/media/profile_pics/',
            msg_prefix="Profile picture should be displayed on the page."
        )

    def test_uploads_display(self):
        """
        Test that the user's uploads are displayed on the profile detail page.
        """
        response = self.client.get(reverse('profile-detail', args=[self.user.id]))
        self.assertContains(response, "Test upload 1", msg_prefix="Caption of first upload should be visible.")
        self.assertContains(response, "Test upload 2", msg_prefix="Caption of second upload should be visible.")
        self.assertContains(
            response,
            'src="/media/',
            msg_prefix="Uploaded images should be displayed on the page."
        )


from django.test import TestCase
from users.models import Message

from django.test import TestCase

from django.contrib.messages import get_messages

class SendMessageViewTest(TestCase):
    """
    Test suite for the `send_message` view.
    """

    def setUp(self):
        """
        Set up test users and client.
        """
        # Create a sender and a receiver
        self.sender = User.objects.create_user(username="sender", password="password123")
        self.receiver = User.objects.create_user(username="receiver", password="password456")
        self.client.login(username="sender", password="password123")

    def test_send_message_success(self):
        """
        Test that a valid message is sent and redirects to the message thread.
        """
        response = self.client.post(
            reverse("send_message", args=[self.receiver.id]),
            {"content": "Hello, this is a test message."}
        )

        # Assert the message was saved in the database
        self.assertTrue(
            Message.objects.filter(sender=self.sender, recipient=self.receiver, content="Hello, this is a test message.").exists()
        )

        # Assert the redirection is to the message thread
        self.assertRedirects(response, reverse("message-thread", args=[self.receiver.id]))

    def test_send_message_empty_content(self):
        """
        Test that sending an empty message does not save it and redirects back to the profile detail page.
        """
        response = self.client.post(
            reverse("send_message", args=[self.receiver.id]),
            {"content": ""},
        )

        # Assert no message was saved
        self.assertFalse(
            Message.objects.filter(sender=self.sender, recipient=self.receiver).exists()
        )

        # Assert redirection back to the receiver's profile page
        self.assertRedirects(response, reverse("profile-detail", args=[self.receiver.id]))

    def test_send_message_to_nonexistent_user(self):
        """
        Test that sending a message to a non-existent user returns a 404 error.
        """
        non_existent_user_id = self.receiver.id + 1
        response = self.client.post(
            reverse("send_message", args=[non_existent_user_id]),
            {"content": "Hello, this is a test message."},
        )

        # Assert the response is a 404 error
        self.assertEqual(response.status_code, 404)

    def test_send_message_unauthenticated(self):
        """
        Test that unauthenticated users cannot send messages.
        """
        self.client.logout()
        response = self.client.post(
            reverse("send_message", args=[self.receiver.id]),
            {"content": "Hello, this is a test message."},
        )

        # Assert redirection to login page
        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('send_message', args=[self.receiver.id])}",
            msg_prefix="Unauthenticated users should be redirected to the login page."
        )

    def test_form_submission_redirects_to_message_thread(self):
        """
        Test that sending a message redirects the sender to the message thread with the receiver.
        """
        response = self.client.post(
            reverse("send_message", args=[self.receiver.id]),
            {"content": "Hello, this is a test message!"}
        )
        # Check if it redirects to the correct message thread URL
        self.assertRedirects(
            response,
            reverse("message-thread", args=[self.receiver.id]),
            msg_prefix="The user should be redirected to the message thread after sending a message."
        )

    def test_form_submission_with_no_content_shows_error_message(self):
        """
        Test that sending an empty message does not save it and displays an error message.
        """
        response = self.client.post(
            reverse("send_message", args=[self.receiver.id]),
            {"content": ""}
        )
        # Ensure the response redirects to the profile detail page
        self.assertRedirects(
            response,
            reverse("profile-detail", args=[self.receiver.id]),
            msg_prefix="The user should be redirected to the profile detail page if the message is empty."
        )
        # Check for error messages in the response
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("Message content cannot be empty." in str(message) for message in messages),
            "An appropriate error message should be shown when sending an empty message."
        )

    def test_form_submission_no_redirect_bug(self):
        """
        Test that the form submission actually performs a redirect and does not reload the same page.
        """
        response = self.client.post(
            reverse("send_message", args=[self.receiver.id]),
            {"content": "Test message to check redirect functionality."}
        )
        self.assertNotEqual(
            response.status_code,
            200,
            "The form submission should not return a 200 status; it must redirect."
        )
        self.assertRedirects(
            response,
            reverse("message-thread", args=[self.receiver.id]),
            msg_prefix="The form submission should redirect to the message thread."
        )

    def test_form_not_submitted_with_get_request(self):
        """
        Test that the send_message view does not process a GET request and redirects back to the profile page.
        """
        response = self.client.get(reverse("send_message", args=[self.receiver.id]))
        self.assertRedirects(
            response,
            reverse("profile-detail", args=[self.receiver.id]),
            msg_prefix="GET requests to send_message should redirect back to the profile detail page."
        )
        # Ensure no message is saved
        self.assertFalse(
            Message.objects.filter(sender=self.sender, recipient=self.receiver).exists(),
            "No message should be saved on a GET request to send_message."
        )

    def test_get_request_redirects_to_profile(self):
        """
        Test that a GET request to the send_message view does not process the message and redirects back.
        """
        response = self.client.get(reverse('send_message', args=[self.receiver.id]))
        self.assertRedirects(response, reverse('profile-detail', args=[self.receiver.id]))


from django.test import TestCase
import datetime

class InboxViewTest(TestCase):
    def setUp(self):
        # Create two users for messaging
        self.user1 = User.objects.create_user(username="user1", password="password")
        self.user2 = User.objects.create_user(username="user2", password="password")

    def test_access_inbox_authenticated(self):
        # Log in as user1
        self.client.login(username="user1", password="password")
        response = self.client.get(reverse("inbox"))
        self.assertEqual(response.status_code, 200)

    def test_access_inbox_unauthenticated(self):
        response = self.client.get(reverse("inbox"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('inbox')}")

    def test_display_received_messages(self):
        # Create messages
        Message.objects.create(
            sender=self.user2,
            recipient=self.user1,
            content="Message 1",
            timestamp=datetime.datetime.now() - datetime.timedelta(days=1)
        )
        Message.objects.create(
            sender=self.user2,
            recipient=self.user1,
            content="Message 2",
            timestamp=datetime.datetime.now()
        )

        # Log in as user1 and fetch inbox
        self.client.login(username="user1", password="password")
        response = self.client.get(reverse("inbox"))
        messages = response.context['messages']

        # Assert order and content
        self.assertEqual(messages[0].content, "Message 2")
        self.assertEqual(messages[1].content, "Message 1")

    def test_empty_inbox(self):
        self.client.login(username="user1", password="password")
        response = self.client.get(reverse("inbox"))
        self.assertContains(response, "No messages.")

from django.test import TestCase

from django.test import TestCase

class MessageThreadViewTest(TestCase):
    """Test cases for the message_thread view."""

    def setUp(self):
        """
        Set up test users, messages, and authentication for the test cases.
        """
        self.user1 = User.objects.create_user(username="user1", password="password1")
        self.user2 = User.objects.create_user(username="user2", password="password2")
        self.user3 = User.objects.create_user(username="user3", password="password3")
        self.client.login(username="user1", password="password1")
        self.message1 = Message.objects.create(sender=self.user1, recipient=self.user2, content="Message 1")
        self.message2 = Message.objects.create(sender=self.user2, recipient=self.user1, content="Message 2")

    def test_access_message_thread_unauthenticated(self):
        """Ensure unauthenticated users cannot access the message thread."""
        self.client.logout()
        response = self.client.get(reverse("message-thread", args=[self.user2.id]))
        self.assertRedirects(response, f"/users/login/?next=/users/message_thread/{self.user2.id}/")

    def test_empty_message_not_sent(self):
        """Ensure an empty message is not saved and shows an error."""
        response = self.client.post(reverse("message-thread", args=[self.user2.id]), {"content": ""}, follow=True)
        self.assertContains(response, "Message cannot be empty.")  # Ensure the error message is displayed.
        self.assertEqual(Message.objects.count(), 2)  # Ensure no new message is created.

    def test_thread_with_no_messages(self):
        """Ensure the thread view handles cases where there are no messages."""
        response = self.client.get(reverse("message-thread", args=[self.user3.id]))
        self.assertContains(response, "No messages in this thread.")  # Ensure placeholder text is shown.

    def test_user_cannot_access_other_threads(self):
        """Ensure users cannot access threads they are not a part of."""
        self.client.login(username="user3", password="password3")  # Login as a third party.
        response = self.client.get(reverse("message-thread", args=[self.user2.id]))
        self.assertEqual(response.status_code, 403)  # Expect forbidden status code.

from django.utils import timezone
from datetime import timedelta

class HiringRequestTestCase(TestCase):
    def setUp(self):
        # Setup three users: A, B (recipient), C
        self.sender_a = User.objects.create_user(username="sender_a", password="password123")
        self.sender_c = User.objects.create_user(username="sender_c", password="password123")
        self.recipient_b = User.objects.create_user(username="recipient_b", password="password123")

        self.hiring_date = timezone.now().date() + timedelta(days=1)  # Hiring for tomorrow

    def login_as(self, user):
        self.client.logout()
        self.client.login(username=user.username, password="password123")

    def test_hiring_acceptance_and_auto_decline(self):
        # Sender A sends hiring request
        self.login_as(self.sender_a)
        response = self.client.post(
            reverse("message-thread", args=[self.recipient_b.id]),
            {"hiring_request": "true", "date": self.hiring_date, "time": "10:00", "location": "Cafe"}
        )
        self.assertRedirects(response, reverse("message-thread", args=[self.recipient_b.id]))

        # Sender C sends another hiring request for same recipient/date
        self.login_as(self.sender_c)
        response = self.client.post(
            reverse("message-thread", args=[self.recipient_b.id]),
            {"hiring_request": "true", "date": self.hiring_date, "time": "11:00", "location": "Library"}
        )
        self.assertRedirects(response, reverse("message-thread", args=[self.recipient_b.id]))

        # Assert both pending requests exist
        self.assertEqual(Message.objects.filter(recipient=self.recipient_b, hiring_status="pending").count(), 2)

        # Recipient B accepts Sender A's request
        self.login_as(self.recipient_b)
        hire_message = Message.objects.filter(sender=self.sender_a, recipient=self.recipient_b, hiring_status="pending").first()
        response = self.client.post(
            reverse("message-thread", args=[hire_message.sender.id]),
            {"hiring_action": "accept", "message_id": hire_message.id}
        )
        self.assertRedirects(response, reverse("message-thread", args=[hire_message.sender.id]))

        # Reload from DB
        hire_message.refresh_from_db()
        other_hire_message = Message.objects.filter(sender=self.sender_c, recipient=self.recipient_b).first()

        # Assert accepted message is accepted
        self.assertEqual(hire_message.hiring_status, "accepted")

        # Assert conflicting pending requests are declined
        self.assertEqual(other_hire_message.hiring_status, "declined")

    def test_hiring_blocked_after_acceptance(self):
        # Sender A sends hiring request
        self.login_as(self.sender_a)
        self.client.post(
            reverse("message-thread", args=[self.recipient_b.id]),
            {"hiring_request": "true", "date": self.hiring_date, "time": "10:00", "location": "Cafe"}
        )

        # Recipient B accepts Sender A's hiring
        self.login_as(self.recipient_b)
        hire_message = Message.objects.filter(sender=self.sender_a, recipient=self.recipient_b, hiring_status="pending").first()
        self.client.post(
            reverse("message-thread", args=[hire_message.sender.id]),
            {"hiring_action": "accept", "message_id": hire_message.id}
        )

        # Sender C now tries to send another hiring for same date
        self.login_as(self.sender_c)
        response = self.client.post(
            reverse("message-thread", args=[self.recipient_b.id]),
            {"hiring_request": "true", "date": self.hiring_date, "time": "12:00", "location": "Park"},
            follow=True
        )

        # Check for error message about already being hired
        self.assertContains(response, "already hired for the selected date", status_code=200)

        # Ensure no new pending hiring created
        pending_hirings = Message.objects.filter(
            sender=self.sender_c,
            recipient=self.recipient_b,
            date=self.hiring_date,
            hiring_status="pending"
        )
        self.assertEqual(pending_hirings.count(), 0)




from django.test import TestCase

class HiringRequestSelfConflictTestCase(TestCase):
    def setUp(self):
        # Setup two users: Sender (A) and Recipient (B)
        self.sender_a = User.objects.create_user(username="sender_a", password="password123")
        self.recipient_b = User.objects.create_user(username="recipient_b", password="password123")
        self.hiring_date = timezone.now().date() + timedelta(days=1)

    def login_as(self, user):
        self.client.logout()
        self.client.login(username=user.username, password="password123")

    def test_sender_cannot_rehire_accepted_recipient_same_date(self):
        # Sender A sends hiring request to Recipient B
        self.login_as(self.sender_a)
        self.client.post(
            reverse("message-thread", args=[self.recipient_b.id]),
            {"hiring_request": "true", "date": self.hiring_date, "time": "10:00", "location": "Cafe"}
        )

        # Recipient B accepts the hiring request
        self.login_as(self.recipient_b)
        hire_message = Message.objects.filter(sender=self.sender_a, recipient=self.recipient_b, hiring_status="pending").first()
        self.client.post(
            reverse("message-thread", args=[hire_message.sender.id]),
            {"hiring_action": "accept", "message_id": hire_message.id}
        )

        # Now Sender A tries to send another hiring request for same date
        self.login_as(self.sender_a)
        response = self.client.post(
            reverse("message-thread", args=[self.recipient_b.id]),
            {"hiring_request": "true", "date": self.hiring_date, "time": "12:00", "location": "Park"},
            follow=True
        )

        # Should block this second hiring
        self.assertContains(response, "already hired for the selected date", status_code=200)

        # Ensure no new pending hiring created
        pending_hirings = Message.objects.filter(
            sender=self.sender_a,
            recipient=self.recipient_b,
            date=self.hiring_date,
            hiring_status="pending"
        )
        self.assertEqual(pending_hirings.count(), 0)


