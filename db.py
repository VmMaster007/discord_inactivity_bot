# db.py
# SQLite helpers for the inactivity bot

import sqlite3
import time
from typing import Optional, List, Tuple
from datetime import datetime, timezone, timedelta

DB_PATH = "activity.db"

def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection."""
    return sqlite3.connect(DB_PATH)

def init_db() -> None:
    """Create the activity table if it doesn't exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS activity (
            guild_id    INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            username    TEXT,
            last_active INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )

    conn.commit()
    conn.close()

def update_last_active(guild_id: int, user_id: int, username: str) -> None:
    """Set last_active to 'now' for this guild/user."""
    now_ts = int(time.time())
    conn = get_connection()
    cur = conn.cursor()

    guild.id,
    author.id,
    author.display_name,

    cur.execute(
    """
    INSERT INTO activity (guild_id, user_id, username, last_active)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(guild_id, user_id) DO UPDATE
        SET last_active = excluded.last_active,
            username = excluded.username
    """,
    (guild_id, user_id, username, now_ts),
    )

    conn.commit()
    conn.close()

def get_last_active(guild_id: int, user_id: int) -> Optional[int]:
    """Return last_active timestamp for a user, or None if unknown."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT last_active
        FROM activity
        WHERE guild_id = ?
          AND user_id = ?
        """,
        (guild_id, user_id),
    )

    row = cur.fetchone()
    conn.close()

    if row is None:
        return None

    return row[0]

def get_inactive_users(guild_id: int, cutoff_ts: int) -> List[Tuple[int, int]]:
    """
    Return a list of (user_id, last_active_ts) for members whose
    last_active <= cutoff_ts.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT user_id, last_active
        FROM activity
        WHERE guild_id = ?
          AND last_active IS NOT NULL
          AND last_active <= ?
        """,
        (guild_id, cutoff_ts),
    )

    rows = cur.fetchall()
    conn.close()

    return rows

def ensure_guild_settings(guild_id: int, guild_name: str | None = None) -> None:
    """Make sure a row exists in dashboard_guildsettings for this guild."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Create a default row if it doesn't exist
    cur.execute(
        """
        INSERT OR IGNORE INTO dashboard_guildsettings (
            guild_id,
            guild_name,
            inactivity_days,
            auto_kick_enabled,
            inactivity_notifications_enabled,
            afk_system_enabled,
            quiet_ping_enabled,
            last_updated
        )
        VALUES (?, COALESCE(?, ''), 14, 1, 1, 1, 1, CURRENT_TIMESTAMP)
        """,
        (guild_id, guild_name),
    )

    # Keep guild_name up to date
    if guild_name is not None:
        cur.execute(
            """
            UPDATE dashboard_guildsettings
            SET guild_name = ?, last_updated = CURRENT_TIMESTAMP
            WHERE guild_id = ?
            """,
            (guild_name, guild_id),
        )

    conn.commit()
    conn.close()

def get_guild_settings(guild_id: int) -> dict:
    """Return settings for a guild as a dict, with sensible defaults."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM dashboard_guildsettings WHERE guild_id = ?", (guild_id,)
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        # If somehow missing, create a default in the DB and return defaults
        ensure_guild_settings(guild_id)
        return {
            "guild_id": guild_id,
            "guild_name": "",
            "inactivity_days": 14,
            "auto_kick_enabled": 1,
            "inactivity_notifications_enabled": 1,
            "afk_system_enabled": 1,
            "quiet_ping_enabled": 1,
        }

    return dict(row)