from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('login/', views.signin, name='login'),
    path('profile/', views.profile, name='profile'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('global-feed/', views.global_feed, name='global-feed'),
    path('profile/<int:user_id>/', views.profile_detail, name='profile-detail'),
    path('send_message/<int:user_id>/', views.send_message, name='send_message'),
    path('inbox/', views.inbox, name='inbox'),
    path('message_thread/<int:user_id>/', views.message_thread, name='message-thread'),
]
