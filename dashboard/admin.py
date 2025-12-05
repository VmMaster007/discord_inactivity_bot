from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import GuildSettings


@admin.register(GuildSettings)
class GuildSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "guild_name",
        "guild_id",
        "inactivity_days",
        "auto_kick_enabled",
        "inactivity_notifications_enabled",
        "afk_system_enabled",
        "quiet_ping_enabled",
        "last_updated",
    )
    list_editable = (
        "inactivity_days",
        "auto_kick_enabled",
        "inactivity_notifications_enabled",
        "afk_system_enabled",
        "quiet_ping_enabled",
    )
    search_fields = ("guild_name", "guild_id")
