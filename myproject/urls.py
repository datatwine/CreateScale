"""
URL configuration for myproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('users/', include('users.urls')),  # Include the 'users' app's URLs
    path('silk/', include('silk.urls', namespace='silk')),
    # Custom LinkedIn adapter routes (must come BEFORE allauth catch-all)
    # because allauth's built-in linkedin_oauth2 adapter uses deprecated V1 endpoints
    path("accounts/linkedin_oauth2/login/",
         __import__('users.linkedin_adapter', fromlist=['oauth2_login']).oauth2_login,
         name="linkedin_oauth2_login"),
    path("accounts/linkedin_oauth2/login/callback/",
         __import__('users.linkedin_adapter', fromlist=['oauth2_callback']).oauth2_callback,
         name="linkedin_oauth2_callback"),
    path("accounts/", include("allauth.urls")),  # adds /accounts/google/login/ etc.
    path("bookings/", include("bookings.urls")),
    path("", include("django_prometheus.urls")),
    path("api/", include("users.api.urls")),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
