from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("settings/guilds/", views.guild_settings_list, name="guild_settings_list"),
    path("settings/guilds/<int:guild_id>/", views.edit_guild_settings, name="guild_settings_edit"),

    path("activity/", views.activity_list, name="activity_list"),

    path("toggle/auto-kick/<int:guild_id>/", views.toggle_auto_kick, name="toggle_auto_kick"),
    path("toggle/notifications/<int:guild_id>/", views.toggle_notifications, name="toggle_notifications"),
    path("toggle/afk/<int:guild_id>/", views.toggle_afk, name="toggle_afk"),

    path("tickets/", views.tickets_settings, name="tickets_settings"),
    path("exemptions/", views.kick_exemptions, name="kick_exemptions"),
    path("guild/select/<int:guild_id>/", views.set_current_guild, name="set_current_guild"),
]
