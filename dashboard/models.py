from django.db import models

# Create your models here.
from django.db import models

class GuildSettings(models.Model):
    guild_id = models.BigIntegerField(primary_key=True)
    guild_name = models.CharField(max_length=100, blank=True)

    inactivity_days = models.PositiveIntegerField(default=14)
    auto_kick_enabled = models.BooleanField(default=True)
    inactivity_notifications_enabled = models.BooleanField(default=True)
    afk_system_enabled = models.BooleanField(default=True)
    quiet_ping_enabled = models.BooleanField(default=True)

    last_updated = models.DateTimeField(auto_now=True)

    # Ticket system settings
    tickets_enabled = models.BooleanField(default=True)

    ticket_panel_channel_id = models.BigIntegerField(null=True, blank=True)

    ticket_panel_title = models.CharField(max_length=100, default="Ticket")
    ticket_panel_description = models.TextField(default="To create a ticket click 📩 below.")

    staff_role_id = models.BigIntegerField(null=True, blank=True)
    support_category_id = models.BigIntegerField(null=True, blank=True)
    bug_reports_channel_id = models.BigIntegerField(null=True, blank=True)
    afk_approval_channel_id = models.BigIntegerField(null=True, blank=True)




    def __str__(self) -> str:
        return self.guild_name or str(self.guild_id)
