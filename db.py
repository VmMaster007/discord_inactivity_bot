import time
import sqlite3
from pathlib import Path

# Path to the SQLite database file (in the project root)
DB_PATH = Path(__file__).parent / "activity.db"


def get_connection() -> sqlite3.Connection:
    """
    Open a connection to the SQLite database.
    Caller is responsible for closing it.
    """
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """
    Create the user_activity table if it doesn't exist yet.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_activity (
                guild_id       TEXT    NOT NULL,
                user_id        TEXT    NOT NULL,
                last_active_ts INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

def update_last_active(guild_id: int, user_id: int, timestamp: int | None = None) -> None:
    """
    Insert or update the last_active_ts for a given user in a given guild.
    Uses a Unix timestamp (int seconds since epoch).
    """
    if timestamp is None:
        timestamp = int(time.time())

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_activity (guild_id, user_id, last_active_ts)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET last_active_ts = excluded.last_active_ts;
            """,
            (str(guild_id), str(user_id), timestamp),
        )
        conn.commit()
    finally:
        conn.close()
