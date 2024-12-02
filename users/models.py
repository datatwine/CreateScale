
# Create your models here.
from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE) 
    profession = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=100, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    bio = models.CharField(max_length=140, blank=True)

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

    def __str__(self):
        return f'Message from {self.sender} to {self.recipient}'

