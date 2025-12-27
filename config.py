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

# ---------------- XP/COINS SYSTEM ----------------

# Channel IDs (right click channel -> Copy ID)
LEADERBOARD_CHANNEL_ID = 1453037552096510176          # REQUIRED: set this
ANNOUNCEMENTS_CHANNEL_ID = 1445181772005638204        # REQUIRED: set this

# How often to edit/update the leaderboard message
LEADERBOARD_UPDATE_MINUTES = 10

# Weekly winner role name (bot will create if missing)
WEEKLY_CHAMP_ROLE_NAME = "👑 Weekly Champ"

# Command cooldowns (seconds)
INVESTIGATE_COOLDOWN_SECONDS = 600  # 10 minutes

# Default XP settings (per day caps handled by DB)
DEFAULT_MSG_XP = 1
DEFAULT_MSG_DAILY_CAP = 50

DEFAULT_VOICE_XP_PER_MIN = 2
DEFAULT_VOICE_DAILY_CAP = 240


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

# ------------------------ TICKETS CONFIG ------------------------

# ------------------------ TICKETS CONFIG ------------------------

# Channel where the bot will create ticket threads (this is where you post /ticketpanel)
TICKETS_INTAKE_CHANNEL_ID = 1454491287595126785  # <-- paste your channel ID here

# Role to ping when user selects "Talk to staff"
STAFF_ROLE_ID = 1444715664110649394

# Where bug reports get forwarded (MODS ONLY channel)
BUG_REPORTS_CHANNEL_ID = 1454503402674458787 # <-- set this to a private mods-only channel ID

# Category where staff-support ticket CHANNELS are created
SUPPORT_CATEGORY_ID = 1454496166501941298 # <-- set this to your "Support" category ID

# AFK exemption approval channel (mods only)
AFK_APPROVAL_CHANNEL_ID = 1454513818381189130 # <-- set this


# Timezone for display
UK_TZ = ZoneInfo("Europe/London")

def format_timestamp(ts: int) -> str:
    """Turn a UNIX timestamp into a UK time string."""
    dt = datetime.fromtimestamp(ts, tz=UK_TZ)
    # Example: 03/12/2025 21:47 GMT
    return dt.strftime("%d/%m/%Y %H:%M:%S %Z")
