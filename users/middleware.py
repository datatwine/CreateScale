# users/middleware.py
from django.utils.deprecation import MiddlewareMixin
from users.models import Profile

class EnsureProfileMiddleware(MiddlewareMixin):
    def process_request(self, request):
        u = getattr(request, "user", None)
        if u and u.is_authenticated:
            Profile.objects.get_or_create(user=u)
