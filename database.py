import sqlite3
from contextlib import contextmanager

DB_PATH = "cricket_bot.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                matches INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                high_score INTEGER DEFAULT 0,
                total_runs INTEGER DEFAULT 0,
                total_wickets INTEGER DEFAULT 0,
                centuries INTEGER DEFAULT 0,
                fifties INTEGER DEFAULT 0,
                hattricks INTEGER DEFAULT 0
            )
            """
        )


def get_player(user_id, username=None):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM players WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO players (user_id, username) VALUES (?, ?)", (user_id, username)
            )
            row = conn.execute("SELECT * FROM players WHERE user_id=?", (user_id,)).fetchone()
        elif username and row["username"] != username:
            conn.execute("UPDATE players SET username=? WHERE user_id=?", (username, user_id))
        return dict(row)


def update_player(user_id, **kwargs):
    if not kwargs:
        return
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [user_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE players SET {cols} WHERE user_id=?", vals)


def record_match_result(user_id, username, won, score, wickets_taken, hattrick=False):
    player = get_player(user_id, username)
    updates = {
        "matches": player["matches"] + 1,
        "wins": player["wins"] + (1 if won else 0),
        "losses": player["losses"] + (0 if won else 1),
        "high_score": max(player["high_score"], score),
        "total_runs": player["total_runs"] + score,
        "total_wickets": player["total_wickets"] + wickets_taken,
        "centuries": player["centuries"] + (1 if score >= 100 else 0),
        "fifties": player["fifties"] + (1 if 50 <= score < 100 else 0),
        "hattricks": player["hattricks"] + (1 if hattrick else 0),
    }
    update_player(user_id, **updates)


def get_leaderboard(limit=10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT username, wins, high_score, matches FROM players "
            "ORDER BY wins DESC, high_score DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
