from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),  # root -> overview
    path("settings/guilds/", views.guild_settings_list, name="guild_settings_list"),
]
