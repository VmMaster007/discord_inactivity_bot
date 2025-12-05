from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import GuildSettings


@login_required
def overview(request):
    """Main dashboard overview page."""
    guilds = GuildSettings.objects.all()

    total_guilds = guilds.count()
    auto_kick_on = guilds.filter(auto_kick_enabled=True).count()
    notifications_on = guilds.filter(inactivity_notifications_enabled=True).count()
    afk_on = guilds.filter(afk_system_enabled=True).count()
    quiet_ping_on = guilds.filter(quiet_ping_enabled=True).count()

    context = {
        "total_guilds": total_guilds,
        "auto_kick_on": auto_kick_on,
        "notifications_on": notifications_on,
        "afk_on": afk_on,
        "quiet_ping_on": quiet_ping_on,
    }
    return render(request, "dashboard/overview.html", context)


@login_required
def guild_settings_list(request):
    """List of guilds + their key settings."""
    guilds = GuildSettings.objects.all().order_by("guild_name", "guild_id")
    return render(
        request,
        "dashboard/guild_settings_list.html",
        {"guilds": guilds},
    )
