# db.py
# SQLite helpers for the inactivity bot

import sqlite3
import time
from typing import Optional, List, Tuple

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
            last_active INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )

    conn.commit()
    conn.close()


def update_last_active(guild_id: int, user_id: int) -> None:
    """Set last_active to 'now' for this guild/user."""
    now_ts = int(time.time())
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO activity (guild_id, user_id, last_active)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE
            SET last_active = excluded.last_active
        """,
        (guild_id, user_id, now_ts),
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
