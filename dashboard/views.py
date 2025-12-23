from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import connections
from datetime import datetime, timezone
from django.utils.timezone import make_aware, is_naive

from .models import GuildSettings
from .forms import GuildSettingsForm


@login_required
def overview(request):
    """Main dashboard overview page (single-guild focus)."""
    guilds = GuildSettings.objects.all().order_by("guild_name", "guild_id")
    total_guilds = guilds.count()

    # Use the first/only guild as the "current" one for ON/OFF toggles
    current_guild = guilds.first()

    context = {
        "total_guilds": total_guilds,
        "current_guild": current_guild,

        # Booleans for THIS server
        "auto_kick_on": bool(current_guild and current_guild.auto_kick_enabled),
        "notifications_on": bool(current_guild and current_guild.inactivity_notifications_enabled),
        "afk_on": bool(current_guild and current_guild.afk_system_enabled),

        # If you want to add a toggle later
        "quiet_ping_on": bool(current_guild and current_guild.quiet_ping_enabled),
    }
    return render(request, "dashboard/overview.html", context)


@login_required
def guild_settings_list(request):
    """List of guilds + their key settings."""
    guilds = GuildSettings.objects.all().order_by("guild_name", "guild_id")
    return render(request, "dashboard/guild_settings_list.html", {"guilds": guilds})


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

    return render(
        request,
        "dashboard/guild_settings_edit.html",
        {"guild_settings": guild_settings, "form": form},
    )


@login_required
@require_POST
def toggle_auto_kick(request, guild_id):
    guild = get_object_or_404(GuildSettings, pk=guild_id)
    guild.auto_kick_enabled = not guild.auto_kick_enabled
    guild.save(update_fields=["auto_kick_enabled"])
    messages.success(request, f"Auto kick set to {'ON' if guild.auto_kick_enabled else 'OFF'} for {guild.guild_name}.")
    return redirect("dashboard:overview")


@login_required
@require_POST
def toggle_notifications(request, guild_id):
    guild = get_object_or_404(GuildSettings, pk=guild_id)
    guild.inactivity_notifications_enabled = not guild.inactivity_notifications_enabled
    guild.save(update_fields=["inactivity_notifications_enabled"])
    messages.success(
        request,
        f"Inactivity notifications set to {'ON' if guild.inactivity_notifications_enabled else 'OFF'} for {guild.guild_name}."
    )
    return redirect("dashboard:overview")


@login_required
@require_POST
def toggle_afk(request, guild_id):
    guild = get_object_or_404(GuildSettings, pk=guild_id)
    guild.afk_system_enabled = not guild.afk_system_enabled
    guild.save(update_fields=["afk_system_enabled"])
    messages.success(request, f"AFK system set to {'ON' if guild.afk_system_enabled else 'OFF'} for {guild.guild_name}.")
    return redirect("dashboard:overview")

@login_required
def activity_list(request):
    current_guild = GuildSettings.objects.all().order_by("guild_name", "guild_id").first()

    users = []
    if current_guild:
        with connections["bot"].cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, username, last_active
                FROM activity
                WHERE guild_id = %s
                ORDER BY last_active DESC
                """,
                [current_guild.guild_id],
            )
            rows = cursor.fetchall()

        for user_id, username, last_active in rows:
            dt = None
            if last_active is not None:
                dt = datetime.fromtimestamp(int(last_active), tz=timezone.utc)

            users.append(
                {
                    "user_id": user_id,
                    "username": username or "Unknown",
                    "last_active": dt,
                }
            )

    return render(
        request,
        "dashboard/activity_list.html",
        {"current_guild": current_guild, "users": users},
    )