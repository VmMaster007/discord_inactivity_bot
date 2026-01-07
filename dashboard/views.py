from datetime import datetime, timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connections
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from db import clear_kick_exemption, list_kick_exemptions
from .forms import GuildSettingsForm
from .models import GuildSettings



@login_required
def overview(request):
    guilds = GuildSettings.objects.all().order_by("guild_name", "guild_id")
    total_guilds = guilds.count()

    # Prefer selected guild from session, else fall back to first guild
    session_guild_id = request.session.get("current_guild_id")
    current_guild = None

    if session_guild_id:
        current_guild = GuildSettings.objects.filter(guild_id=session_guild_id).first()

    if current_guild is None:
        current_guild = guilds.first()
        if current_guild:
            request.session["current_guild_id"] = current_guild.guild_id

    context = {
        "guilds": guilds,
        "total_guilds": total_guilds,
        "current_guild": current_guild,
        "auto_kick_on": bool(current_guild and current_guild.auto_kick_enabled),
        "notifications_on": bool(current_guild and current_guild.inactivity_notifications_enabled),
        "afk_on": bool(current_guild and current_guild.afk_system_enabled),
        "quiet_ping_on": bool(current_guild and current_guild.quiet_ping_enabled),
    }
    return render(request, "dashboard/overview.html", context)

@login_required
def set_current_guild(request, guild_id: int):
    gs = get_object_or_404(GuildSettings, pk=guild_id)
    request.session["current_guild_id"] = gs.guild_id
    messages.success(request, f"Selected guild: {gs.guild_name or gs.guild_id}")
    return redirect("dashboard:overview")


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

def tickets_settings(request):
    guild_id = request.session.get("current_guild_id")
    if not guild_id:
        first = GuildSettings.objects.all().order_by("guild_name", "guild_id").first()
        if not first:
            messages.error(request, "No guilds found yet.")
            return redirect("dashboard:overview")
        guild_id = first.guild_id
        request.session["current_guild_id"] = guild_id

    gs = GuildSettings.objects.get(guild_id=guild_id)

    def to_int(v):
        v = (v or "").strip()
        return int(v) if v else None

    if request.method == "POST":
        gs.tickets_enabled = request.POST.get("tickets_enabled") == "on"

        gs.ticket_panel_channel_id = to_int(request.POST.get("ticket_panel_channel_id"))
        gs.staff_role_id = to_int(request.POST.get("staff_role_id"))
        gs.support_category_id = to_int(request.POST.get("support_category_id"))
        gs.bug_reports_channel_id = to_int(request.POST.get("bug_reports_channel_id"))
        gs.afk_approval_channel_id = to_int(request.POST.get("afk_approval_channel_id"))

        gs.ticket_panel_title = (request.POST.get("ticket_panel_title") or "Ticket").strip()
        gs.ticket_panel_description = (request.POST.get("ticket_panel_description") or "").strip()

        gs.save()
        messages.success(request, "Ticket settings saved.")
        return redirect("dashboard:tickets_settings")

    return render(request, "dashboard/tickets_settings.html", {"gs": gs})

@login_required
def kick_exemptions(request):
    guild_id = request.session.get("current_guild_id")
    if not guild_id:
        first = GuildSettings.objects.all().order_by("guild_name", "guild_id").first()
        if not first:
            messages.error(request, "No guilds found yet.")
            return redirect("dashboard:overview")
        guild_id = first.guild_id
        request.session["current_guild_id"] = guild_id

    if request.method == "POST":
        user_id = int(request.POST.get("user_id"))
        clear_kick_exemption(guild_id, user_id)
        messages.success(request, "Exemption removed.")
        return redirect("dashboard:kick_exemptions")

    rows = list_kick_exemptions(guild_id)
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())

    for r in rows:
        until_dt = datetime.fromtimestamp(int(r["exempt_until"]), tz=timezone.utc)
        r["until_str"] = until_dt.strftime("%d/%m/%Y %H:%M UTC")
        r["active"] = int(r["exempt_until"]) > now_ts

        if r["active"]:
            delta = until_dt - now
            days = delta.days
            hours = delta.seconds // 3600
            r["time_left"] = f"{days}d {hours}h"
        else:
            r["time_left"] = "Expired"

    return render(request, "dashboard/kick_exemptions.html", {"rows": rows})

