from django.urls import path
from . import views

app_name = 'setup'

urlpatterns = [
    path('', views.WelcomeView.as_view(), name='setup_welcome'),
    path('welcome/', views.WelcomeView.as_view(), name='setup_welcome'),
    path('company/', views.CompanyView.as_view(), name='setup_company'),
    path('admin/', views.AdminUserView.as_view(), name='setup_admin'),
    path('modules/', views.ModulesView.as_view(), name='setup_modules'),
    path('configure/', views.ConfigureView.as_view(), name='setup_configure'),
    path('review/', views.ReviewView.as_view(), name='setup_review'),
    path('install/', views.InstallView.as_view(), name='setup_install'),
    path('complete/', views.CompleteView.as_view(), name='setup_complete'),
]