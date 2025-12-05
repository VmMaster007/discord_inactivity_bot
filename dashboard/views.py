from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages

from .models import GuildSettings
from .forms import GuildSettingsForm


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

@login_required
def edit_guild_settings(request, guild_id):
    """Edit settings for a single guild."""
    guild_settings = get_object_or_404(GuildSettings, pk=guild_id)

    if request.method == "POST":
        form = GuildSettingsForm(request.POST, instance=guild_settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved successfully.")
            return redirect("dashboard:guild_settings_list")
    else:
        form = GuildSettingsForm(instance=guild_settings)

    context = {
        "guild_settings": guild_settings,
        "form": form,
    }
    return render(request, "dashboard/guild_settings_edit.html", context)
