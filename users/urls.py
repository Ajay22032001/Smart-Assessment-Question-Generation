from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import logout_user



urlpatterns = [
    path('register/', views.register, name='register'),
    path('edit-profile/', views.profile_edit, name='edit_profile'),
    path('login/', auth_views.LoginView.as_view(template_name='users/login.html'), name='login'),
    path('logout/', views.logout_user, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('tab-close-logout/', views.tab_close_logout, name='tab_close_logout'),
    # path('heartbeat/', views.heartbeat, name='heartbeat'),
    # path('check-tabs/', views.check_tabs, name='check_tabs'),
    
]
