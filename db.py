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
