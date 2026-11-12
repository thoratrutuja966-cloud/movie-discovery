from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [path("admin/", admin.site.urls), path("accounts/login/", auth_views.LoginView.as_view(template_name="discovery/login.html"), name="login"), path("", include("discovery.urls"))]
