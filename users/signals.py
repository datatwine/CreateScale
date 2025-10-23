from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import Profile

from allauth.account.signals import user_signed_up
from django.contrib.auth import get_user_model

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    instance.profile.save()


User = get_user_model()

@receiver(user_signed_up)
def ensure_profile_on_google_signup(request, user, **kwargs):
    # Create a Profile if missing (works for social signups)
    Profile.objects.get_or_create(user=user)