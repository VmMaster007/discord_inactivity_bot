# db.py
# SQLite helpers for the inactivity bot

import sqlite3
import time

DB_PATH = "activity.db"


def get_connection():
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
            last_active INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )

    conn.commit()
    conn.close()


def update_last_active(guild_id: int, user_id: int) -> None:
    """
    Upsert last_active for a given guild + user.
    Called by mark_active() in bot.py.
    """
    now_ts = int(time.time())

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO activity (guild_id, user_id, last_active)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, user_id)
        DO UPDATE SET last_active = excluded.last_active
        """,
        (guild_id, user_id, now_ts),
    )

    conn.commit()
    conn.close()


def get_last_active(guild_id: int, user_id: int) -> int | None:
    """
    Return last_active timestamp for a given user in a guild,
    or None if we have no record.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT last_active
        FROM activity
        WHERE guild_id = ? AND user_id = ?
        """,
        (guild_id, user_id),
    )

    row = cur.fetchone()
    conn.close()

    if row is None:
        return None

    return row[0]


def get_inactive_users(guild_id: int, cutoff_ts: int) -> list[tuple[int, int]]:
    """
    Return [(user_id, last_active), ...] for users in this guild
    whose last_active is <= cutoff_ts.
    Used by:
      - inactivity cleanup
      - notify_inactive_members
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
