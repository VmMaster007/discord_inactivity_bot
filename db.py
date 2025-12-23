# db.py
# SQLite helpers for inactivity + XP/Levels + Ghost Coins + Contracts + Shop

import sqlite3
import time
from typing import Optional, List, Tuple
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
DB_PATH = "activity.db"


# -----------------------------
# Connection helper
# -----------------------------
def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


# -----------------------------
# Date helpers
# -----------------------------
def week_key_now() -> str:
    """Sunday date (YYYY-MM-DD) that starts current week in Europe/London."""
    today = datetime.now(LONDON).date()
    days_since_sunday = (today.weekday() + 1) % 7  # Mon=0..Sun=6 -> Sun becomes 0
    sunday = today.fromordinal(today.toordinal() - days_since_sunday)
    return sunday.isoformat()


def day_key_now() -> str:
    """Today's date (YYYY-MM-DD) in Europe/London."""
    return datetime.now(LONDON).date().isoformat()


def now_utc_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


# -----------------------------
# Level formula
# -----------------------------
def xp_needed_for_next(level: int) -> int:
    # 5*(level^2) + 50*level + 100
    return 5 * (level ** 2) + 50 * level + 100


def compute_level_from_total_xp(total_xp: int) -> tuple[int, int]:
    """
    Returns (level, xp_into_level).
    Level starts at 0. Each level requires xp_needed_for_next(level).
    """
    level = 0
    remaining = total_xp

    while True:
        need = xp_needed_for_next(level)
        if remaining >= need:
            remaining -= need
            level += 1
        else:
            return level, remaining


# -----------------------------
# DB init
# -----------------------------
def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    # Inactivity activity table
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

    # Weekly XP (leaderboards)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS xp_weekly (
            guild_id   INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            week_key   TEXT NOT NULL,
            points     INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id, week_key)
        )
        """
    )

    # Daily caps per source
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS xp_daily_caps (
            guild_id      INTEGER NOT NULL,
            user_id       INTEGER NOT NULL,
            day_key       TEXT NOT NULL,
            source        TEXT NOT NULL,
            points_earned INTEGER NOT NULL DEFAULT 0,
            updated_at    TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id, day_key, source)
        )
        """
    )

    # Total XP + Level
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_xp (
            guild_id   INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            total_xp   INTEGER NOT NULL DEFAULT 0,
            level      INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )

    # Ghost Coins wallet
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_wallet (
            guild_id   INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            coins      INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )

    # Inventory items (supports timed boosts via expires_at_ts)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_inventory (
            guild_id        INTEGER NOT NULL,
            user_id         INTEGER NOT NULL,
            item_key        TEXT NOT NULL,
            qty             INTEGER NOT NULL DEFAULT 0,
            expires_at_ts   INTEGER,
            updated_at      TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id, item_key)
        )
        """
    )

    # Cooldowns
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cooldowns (
            guild_id    INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            command_key TEXT NOT NULL,
            next_ts     INTEGER NOT NULL,
            PRIMARY KEY (guild_id, user_id, command_key)
        )
        """
    )

    # Daily contracts (NOTE: no updated_at column here)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS contracts_daily (
            guild_id      INTEGER NOT NULL,
            user_id       INTEGER NOT NULL,
            day_key       TEXT NOT NULL,
            contract_key  TEXT NOT NULL,
            title         TEXT NOT NULL,
            target        INTEGER NOT NULL,
            progress      INTEGER NOT NULL DEFAULT 0,
            reward_xp     INTEGER NOT NULL,
            reward_coins  INTEGER NOT NULL,
            completed     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, day_key, contract_key)
        )
        """
    )

    conn.commit()
    conn.close()


# -----------------------------
# Inactivity tracking
# -----------------------------
def update_last_active(guild_id: int, user_id: int, username: str) -> None:
    now_ts = int(time.time())
    conn = get_connection()
    cur = conn.cursor()
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
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT last_active FROM activity WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    )
    row = cur.fetchone()
    conn.close()
    return None if row is None else row[0]


def get_inactive_users(guild_id: int, cutoff_ts: int) -> List[Tuple[int, int]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, last_active
        FROM activity
        WHERE guild_id=? AND last_active IS NOT NULL AND last_active <= ?
        """,
        (guild_id, cutoff_ts),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# -----------------------------
# XP award (caps + total XP + weekly)
# -----------------------------
def award_xp(guild_id: int, user_id: int, source: str, amount: int, daily_cap: int) -> dict:
    """
    Awards XP respecting daily cap per source.
    Updates: xp_daily_caps, xp_weekly, user_xp (total + level)
    Returns dict: {awarded:int, leveled_up:bool, new_level:int, total_xp:int}
    """
    if amount <= 0:
        return {"awarded": 0, "leveled_up": False, "new_level": 0, "total_xp": 0}

    wk = week_key_now()
    day = day_key_now()
    now_iso = datetime.now(timezone.utc).isoformat()  # ✅ FIXED: define now_iso

    conn = get_connection()
    cur = conn.cursor()

    # Daily cap
    cur.execute(
        """
        SELECT points_earned FROM xp_daily_caps
        WHERE guild_id=? AND user_id=? AND day_key=? AND source=?
        """,
        (guild_id, user_id, day, source),
    )
    row = cur.fetchone()
    earned_today = row[0] if row else 0

    remaining = max(0, daily_cap - earned_today)
    give = min(amount, remaining)
    if give <= 0:
        conn.close()
        return {"awarded": 0, "leveled_up": False, "new_level": 0, "total_xp": 0}

    # Upsert daily caps
    cur.execute(
        """
        INSERT INTO xp_daily_caps (guild_id, user_id, day_key, source, points_earned, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id, day_key, source)
        DO UPDATE SET points_earned = points_earned + excluded.points_earned,
                      updated_at = excluded.updated_at
        """,
        (guild_id, user_id, day, source, give, now_iso),
    )

    # Upsert weekly
    cur.execute(
        """
        INSERT INTO xp_weekly (guild_id, user_id, week_key, points, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id, week_key)
        DO UPDATE SET points = points + excluded.points,
                      updated_at = excluded.updated_at
        """,
        (guild_id, user_id, wk, give, now_iso),
    )

    # Get current total_xp/level
    cur.execute(
        "SELECT total_xp, level FROM user_xp WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    )
    row = cur.fetchone()
    old_total = row[0] if row else 0
    old_level = row[1] if row else 0

    new_total = old_total + give
    new_level, _xp_into = compute_level_from_total_xp(new_total)
    leveled_up = new_level > old_level

    # Upsert user_xp
    cur.execute(
        """
        INSERT INTO user_xp (guild_id, user_id, total_xp, level, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id)
        DO UPDATE SET total_xp = excluded.total_xp,
                      level = excluded.level,
                      updated_at = excluded.updated_at
        """,
        (guild_id, user_id, new_total, new_level, now_iso),
    )

    conn.commit()
    conn.close()

    return {"awarded": give, "leveled_up": leveled_up, "new_level": new_level, "total_xp": new_total}


# -----------------------------
# Weekly leaderboard helpers
# -----------------------------
def get_top_weekly(guild_id: int, limit: int = 10) -> List[Tuple[int, int]]:
    wk = week_key_now()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, points
        FROM xp_weekly
        WHERE guild_id=? AND week_key=?
        ORDER BY points DESC
        LIMIT ?
        """,
        (guild_id, wk, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_user_weekly_rank(guild_id: int, user_id: int) -> Tuple[int, int]:
    wk = week_key_now()
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT points FROM xp_weekly WHERE guild_id=? AND user_id=? AND week_key=?",
        (guild_id, user_id, wk),
    )
    row = cur.fetchone()
    user_points = row[0] if row else 0

    cur.execute(
        """
        SELECT 1 + COUNT(*)
        FROM xp_weekly
        WHERE guild_id=? AND week_key=? AND points > ?
        """,
        (guild_id, wk, user_points),
    )
    rank = cur.fetchone()[0]
    conn.close()
    return rank, user_points


def reset_weekly(guild_id: int | None = None) -> None:
    conn = get_connection()
    cur = conn.cursor()
    if guild_id is None:
        cur.execute("DELETE FROM xp_weekly")
        cur.execute("DELETE FROM xp_daily_caps")
    else:
        cur.execute("DELETE FROM xp_weekly WHERE guild_id=?", (guild_id,))
        cur.execute("DELETE FROM xp_daily_caps WHERE guild_id=?", (guild_id,))
    conn.commit()
    conn.close()


# -----------------------------
# Coins + inventory
# -----------------------------
def get_coins(guild_id: int, user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT coins FROM user_wallet WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def add_coins(guild_id: int, user_id: int, amount: int) -> int:
    """Add coins (can be negative). Balance will not go below 0. Returns new balance."""
    now_iso = datetime.now(timezone.utc).isoformat()
    current = get_coins(guild_id, user_id)
    new_bal = max(0, current + amount)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_wallet (guild_id, user_id, coins, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id)
        DO UPDATE SET coins = excluded.coins, updated_at = excluded.updated_at
        """,
        (guild_id, user_id, new_bal, now_iso),
    )
    conn.commit()
    conn.close()
    return new_bal


def get_item(guild_id: int, user_id: int, item_key: str) -> tuple[int, Optional[int]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT qty, expires_at_ts FROM user_inventory WHERE guild_id=? AND user_id=? AND item_key=?",
        (guild_id, user_id, item_key),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return 0, None
    return row[0], row[1]


def set_item(guild_id: int, user_id: int, item_key: str, qty: int, expires_at_ts: Optional[int]) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_inventory (guild_id, user_id, item_key, qty, expires_at_ts, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id, item_key)
        DO UPDATE SET qty = excluded.qty,
                      expires_at_ts = excluded.expires_at_ts,
                      updated_at = excluded.updated_at
        """,
        (guild_id, user_id, item_key, qty, expires_at_ts, now_iso),
    )
    conn.commit()
    conn.close()


def consume_item(guild_id: int, user_id: int, item_key: str, amount: int = 1) -> bool:
    qty, exp = get_item(guild_id, user_id, item_key)
    if qty < amount:
        return False
    set_item(guild_id, user_id, item_key, qty - amount, exp)
    return True


def is_boost_active(guild_id: int, user_id: int, item_key: str) -> bool:
    qty, exp = get_item(guild_id, user_id, item_key)
    if qty <= 0:
        return False
    if exp is None:
        return True
    return now_utc_ts() < exp


# -----------------------------
# Cooldowns
# -----------------------------
def get_cooldown(guild_id: int, user_id: int, command_key: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT next_ts FROM cooldowns WHERE guild_id=? AND user_id=? AND command_key=?",
        (guild_id, user_id, command_key),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def set_cooldown(guild_id: int, user_id: int, command_key: str, next_ts: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO cooldowns (guild_id, user_id, command_key, next_ts)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id, command_key)
        DO UPDATE SET next_ts = excluded.next_ts
        """,
        (guild_id, user_id, command_key, next_ts),
    )
    conn.commit()
    conn.close()


# -----------------------------
# Contracts (daily)
# -----------------------------
def get_contracts_for_today(guild_id: int, user_id: int) -> List[dict]:
    day = day_key_now()
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM contracts_daily
        WHERE guild_id=? AND user_id=? AND day_key=?
        """,
        (guild_id, user_id, day),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_contracts_for_today(guild_id: int, user_id: int, contracts: List[dict]) -> None:
    day = day_key_now()
    conn = get_connection()
    cur = conn.cursor()
    for c in contracts:
        cur.execute(
            """
            INSERT OR IGNORE INTO contracts_daily
            (guild_id, user_id, day_key, contract_key, title, target, progress, reward_xp, reward_coins, completed)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, 0)
            """,
            (guild_id, user_id, day, c["contract_key"], c["title"], c["target"], c["reward_xp"], c["reward_coins"]),
        )
    conn.commit()
    conn.close()


def add_contract_progress(
    guild_id: int,
    user_id: int,
    contract_key: str,
    amount: int,
    db_path: str = "activity.db",
) -> list[dict]:
    """
    Adds progress to today's contract for this user.
    Returns a list containing the contract dict ONLY if it was newly completed by this update.
    Otherwise returns [].
    """
    if amount <= 0:
        return []

    day = day_key_now()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1) Read current state
    cur.execute(
        """
        SELECT contract_key, title, target, progress, completed, reward_xp, reward_coins
        FROM contracts_daily
        WHERE guild_id=? AND user_id=? AND day_key=? AND contract_key=?
        """,
        (guild_id, user_id, day, contract_key),
    )
    row = cur.fetchone()

    if row is None:
        conn.close()
        return []

    was_completed = int(row["completed"]) == 1
    old_progress = int(row["progress"])
    target = int(row["target"])

    # If already completed, do NOT return it and do NOT change progress
    if was_completed:
        conn.close()
        return []

    new_progress = min(target, old_progress + amount)
    now_completed = 1 if new_progress >= target else 0

    # 2) Update row (NO updated_at column in your schema)
    cur.execute(
        """
        UPDATE contracts_daily
        SET progress=?, completed=?
        WHERE guild_id=? AND user_id=? AND day_key=? AND contract_key=?
        """,
        (new_progress, now_completed, guild_id, user_id, day, contract_key),
    )

    conn.commit()

    # 3) Only return if it NEWLY completed now
    if now_completed == 1:
        cur.execute(
            """
            SELECT contract_key, title, target, progress, completed, reward_xp, reward_coins
            FROM contracts_daily
            WHERE guild_id=? AND user_id=? AND day_key=? AND contract_key=?
            """,
            (guild_id, user_id, day, contract_key),
        )
        done = cur.fetchone()
        conn.close()
        return [dict(done)]

    conn.close()
    return []


# -----------------------------
# Dashboard guild settings (compat)
# -----------------------------
def ensure_guild_settings(guild_id: int, guild_name: str | None = None) -> None:
    """
    Make sure a row exists in dashboard_guildsettings for this guild.
    NOTE: This table is typically created by your Django dashboard migrations.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

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

    cur.execute("SELECT * FROM dashboard_guildsettings WHERE guild_id = ?", (guild_id,))
    row = cur.fetchone()
    conn.close()

    if row is None:
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


# -----------------------------
# Admin reset
# -----------------------------
def reset_all_progress(guild_id: int) -> None:
    """
    Wipes XP (weekly + total), coins, inventory, cooldowns, and today's contracts for ONE guild.
    """
    day = day_key_now()
    conn = get_connection()
    cur = conn.cursor()

    # XP
    cur.execute("DELETE FROM xp_weekly WHERE guild_id=?", (guild_id,))
    cur.execute("DELETE FROM xp_daily_caps WHERE guild_id=?", (guild_id,))
    cur.execute("DELETE FROM user_xp WHERE guild_id=?", (guild_id,))

    # Coins + inventory
    cur.execute("DELETE FROM user_wallet WHERE guild_id=?", (guild_id,))
    cur.execute("DELETE FROM user_inventory WHERE guild_id=?", (guild_id,))

    # Contracts (today only)
    cur.execute("DELETE FROM contracts_daily WHERE guild_id=? AND day_key=?", (guild_id, day))

    # Cooldowns
    cur.execute("DELETE FROM cooldowns WHERE guild_id=?", (guild_id,))

    conn.commit()
    conn.close()
