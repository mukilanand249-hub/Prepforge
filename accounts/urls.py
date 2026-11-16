from django.urls import path
from .views import register_view, CustomLoginView, custom_logout_view

urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', custom_logout_view, name='logout'),
]
