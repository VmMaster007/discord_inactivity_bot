from datetime import datetime
from zoneinfo import ZoneInfo

# ------------------------ CONFIG CONSTANTS ------------------------

# How many days of inactivity before a user is eligible for kick
INACTIVITY_DAYS = 14

# How many days of inactivity before they show in the daily "notify" message
INACTIVITY_NOTIFY_DAYS = 7

# IDs specific to your server
GUILD_ID = 1442989805666308158          # your main server ID
STAFF_CHANNEL_ID = 1445137949871182150  # where cleanup logs + dry-runs go
INVITE_CHANNEL_ID = 1445176511614418955 # channel the bot will create invites from
NOTIFY_CHANNEL_ID = 1445137949871182150 # channel for daily inactivity summaries
LEAVE_LOG_CHANNEL_ID = 1452786769731784714  # For channel where leavers will be seen

# Roles that should NEVER be kicked
# NOTE: If you're testing and YOU have one of these roles,
# you will NOT appear in cleanup/dry-run results.
PROTECTED_ROLE_IDS = [
    1445172088963993610,  # Bots
    1444715664110649394,  # Moderator
]

# --- Quiet server pings config ---

# How long a channel can be silent before the bot pokes it
QUIET_TIMEOUT_HOURS = 9  # change to whatever you want

# Channels to monitor for silence
QUIET_CHANNEL_IDS = [
    1442989806517747724,  # lounge
]

WELCOME_CHANNEL_ID = 1446632062160207912  # your welcome channel
VERIFIED_ROLE_ID = 1445174648387010722   # your "Verified" role
WELCOME_BG_PATH = "assets/welcome_bg.png"
WELCOME_FONT_PATH = "assets/WelcomeFont.ttf"


# AFK settings
AFK_ROLE_NAME = "👻 AFK Spirit"  # must match the role name in Discord
AFK_INACTIVE_DAYS = 7           # how many days of inactivity before AFK
AFK_NICK_PREFIX = "👻 "          # what to add in front of nicknames

# Games that count as "activity" when played (presence-based)
TRACKED_GAMES = {"Phasmophobia"}

# Timezone for display
UK_TZ = ZoneInfo("Europe/London")


# Shared help text used by both !help and /help
HELP_MESSAGE = (
    "**Phasmocademy Commands**\n"
    "\n"
    "__General__\n"
    "• `!ping` – Bot heartbeat.\n"
    "• `!guildid` – Show this server's ID.\n"
    "\n"
    "__Activity & AFK__\n"
    "• `!lastseen [@user]` – When a member was last active.\n"
    "• `!cleanup_test` – Dry-run inactivity cleanup (admin).\n"
    "\n"
    "__Moderation (prefix)__\n"
    "• `!clear <amount>` – Delete messages (admin).\n"
    "• `!kick @user [reason]` – Kick a member (admin).\n"
    "• `!ban @user [reason]` – Ban a member (admin).\n"
    "• `!unban <user_id>` – Unban a user (admin).\n"
    "\n"
    "__Slash commands (with dropdowns)__\n"
    "• `/help` – Show this help.\n"
    "• `/kick` – Kick member (user picker).\n"
    "• `/ban` – Ban member (user picker).\n"
    "• `/clear` – Clear messages.\n"
    "• `/unban` – Unban by user.\n"
    "\n"
    "Tip: type `/` in the chat bar to see all slash commands."
)


def format_timestamp(ts: int) -> str:
    """Turn a UNIX timestamp into a UK time string."""
    dt = datetime.fromtimestamp(ts, tz=UK_TZ)
    # Example: 03/12/2025 21:47 GMT
    return dt.strftime("%d/%m/%Y %H:%M:%S %Z")
