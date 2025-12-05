from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("settings/guilds/", views.guild_settings_list, name="guild_settings_list"),
    path(
        "settings/guilds/<int:guild_id>/",
        views.edit_guild_settings,
        name="guild_settings_edit",
    ),
]
