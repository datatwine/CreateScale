
# Create your models here.
from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE) 
    profession = models.CharField(max_length=100, blank=True, db_index=True)
    location = models.CharField(max_length=100, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    bio = models.CharField(max_length=140, blank=True)

    # --- Hiring system toggles / flags ---

    # 2) Performer toggle – user decides if they are a performer
    is_performer = models.BooleanField(
        default=False,
        help_text="Tick if you are available to be hired as a performer.",
    )

    # 3 & 4) Client toggle + admin approval
    # User toggles this on profile; admin turns on client_approved in Django admin.
    is_potential_client = models.BooleanField(
        default=False,
        help_text="Tick if you want to hire performers.",
    )
    client_approved = models.BooleanField(
        default=False,
        help_text="Set by admin. Only approved clients may send hire requests.",
    )

    # 15) Blacklists
    performer_blacklisted = models.BooleanField(
        default=False,
        help_text="If true, this user cannot be hired as a performer.",
    )
    client_blacklisted = models.BooleanField(
        default=False,
        help_text="If true, this user cannot hire performers.",
    )

    def __str__(self):
        return f'{self.user.username} Profile'

class Upload(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='uploads')
    image = models.ImageField(upload_to='profile_pics', blank=True, null=True)
    video = models.FileField(upload_to='profile_videos', blank=True, null=True)
    caption = models.TextField(blank=True)
    upload_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.profile.user.username} Upload on {self.upload_date}'
    

class Message(models.Model):
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='received_messages', on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

        # New Hiring-specific fields
    date = models.DateField(null=True, blank=True)
    time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    hiring_status = models.CharField(max_length=10, choices=[
        ('none', 'None'),
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ], default='none')

    def __str__(self):
        return f'Message from {self.sender} to {self.recipient}'

