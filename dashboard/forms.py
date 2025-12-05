# dashboard/forms.py

from django import forms
from .models import GuildSettings


class GuildSettingsForm(forms.ModelForm):
    class Meta:
        model = GuildSettings
        fields = [
            "inactivity_days",
            "auto_kick_enabled",
            "inactivity_notifications_enabled",
            "afk_system_enabled",
            "quiet_ping_enabled",
        ]
        labels = {
            "inactivity_days": "Days before a member is considered inactive",
            "auto_kick_enabled": "Automatically kick inactive members",
            "inactivity_notifications_enabled": "Send daily inactivity notifications",
            "afk_system_enabled": "Enable AFK system",
            "quiet_ping_enabled": "Enable quiet channel pings",
        }
        widgets = {
            "inactivity_days": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 1,
                    "max": 365,
                }
            ),
            "auto_kick_enabled": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "inactivity_notifications_enabled": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "afk_system_enabled": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "quiet_ping_enabled": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }
