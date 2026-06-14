import sqlite3
import os
from datetime import datetime
from shared.config import DB_PATH

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()

    # Person counts over time
    c.execute('''
        CREATE TABLE IF NOT EXISTS person_counts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT    NOT NULL,
            count     INTEGER NOT NULL,
            camera_id INTEGER DEFAULT 0
        )
    ''')

    # Individual tracking events
    c.execute('''
        CREATE TABLE IF NOT EXISTS tracking_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id  INTEGER NOT NULL,
            first_seen TEXT    NOT NULL,
            last_seen  TEXT    NOT NULL,
            camera_id  INTEGER DEFAULT 0
        )
    ''')

    # Face analytics events
    c.execute('''
        CREATE TABLE IF NOT EXISTS face_events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT    NOT NULL,
            object_id    INTEGER,
            gender       TEXT,
            age_group    TEXT,
            confidence   REAL,
            camera_id    INTEGER DEFAULT 1,
            is_attentive INTEGER DEFAULT 0
        )
    ''')

    # Migration: add is_attentive to face_events if the table already
    # existed without it (older DBs created before this column existed).
    existing_cols = [row[1] for row in c.execute("PRAGMA table_info(face_events)").fetchall()]
    if 'is_attentive' not in existing_cols:
        c.execute("ALTER TABLE face_events ADD COLUMN is_attentive INTEGER DEFAULT 0")

    # Dwell time events
    c.execute('''
        CREATE TABLE IF NOT EXISTS dwell_events (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id          INTEGER NOT NULL,
            start_time         TEXT    NOT NULL,
            end_time           TEXT,
            duration           REAL    DEFAULT 0,
            camera_id          INTEGER DEFAULT 1,
            attentive_duration REAL    DEFAULT 0
        )
    ''')

    # Migration: add attentive_duration to dwell_events if the table
    # already existed without it (older DBs).
    existing_cols = [row[1] for row in c.execute("PRAGMA table_info(dwell_events)").fetchall()]
    if 'attentive_duration' not in existing_cols:
        c.execute("ALTER TABLE dwell_events ADD COLUMN attentive_duration REAL DEFAULT 0")

    # Ad selection log
    c.execute('''
        CREATE TABLE IF NOT EXISTS ad_selections (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT NOT NULL,
            ad_category  TEXT NOT NULL,
            dominant_age TEXT,
            dominant_gender TEXT,
            person_count INTEGER
        )
    ''')

    # Indexes — speed up the date/period aggregation queries used by
    # the dashboard's day/week/month summaries, especially as tables grow.
    c.execute("CREATE INDEX IF NOT EXISTS idx_person_counts_ts ON person_counts(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_face_events_ts ON face_events(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dwell_events_start ON dwell_events(start_time)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tracking_events_first_seen ON tracking_events(first_seen)")

    conn.commit()
    conn.close()
    print("Database initialized at:", DB_PATH)

def log_person_count(count, camera_id=0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO person_counts (timestamp, count, camera_id) VALUES (?,?,?)",
        (datetime.now().isoformat(), count, camera_id)
    )
    conn.commit()
    conn.close()

def log_face_event(object_id, gender, age_group, confidence, camera_id=1, is_attentive=0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO face_events (timestamp, object_id, gender, age_group, confidence, camera_id, is_attentive) VALUES (?,?,?,?,?,?,?)",
        (datetime.now().isoformat(), object_id, gender, age_group, confidence, camera_id, int(bool(is_attentive)))
    )
    conn.commit()
    conn.close()

def log_dwell_start(object_id, camera_id=1):
    conn = get_connection()
    conn.execute(
        "INSERT INTO dwell_events (object_id, start_time, camera_id) VALUES (?,?,?)",
        (object_id, datetime.now().isoformat(), camera_id)
    )
    conn.commit()
    conn.close()

def log_dwell_end(object_id, camera_id=None, attentive_duration=None):
    conn = get_connection()
    attn = attentive_duration if attentive_duration is not None else 0
    if camera_id is not None:
        conn.execute('''
            UPDATE dwell_events
            SET end_time = ?,
                duration = (julianday(?) - julianday(start_time)) * 86400,
                attentive_duration = ?
            WHERE object_id = ? AND camera_id = ? AND end_time IS NULL
        ''', (datetime.now().isoformat(), datetime.now().isoformat(), attn, object_id, camera_id))
    else:
        # Backward-compatible: closes the most recent matching open row
        # regardless of camera. Prefer passing camera_id to avoid
        # cross-camera object_id collisions (both trackers assign small
        # sequential IDs starting from 0).
        conn.execute('''
            UPDATE dwell_events
            SET end_time = ?,
                duration = (julianday(?) - julianday(start_time)) * 86400,
                attentive_duration = ?
            WHERE object_id = ? AND end_time IS NULL
        ''', (datetime.now().isoformat(), datetime.now().isoformat(), attn, object_id))
    conn.commit()
    conn.close()

def log_ad_selection(ad_category, dominant_age, dominant_gender, person_count):
    conn = get_connection()
    conn.execute(
        "INSERT INTO ad_selections (timestamp, ad_category, dominant_age, dominant_gender, person_count) VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(), ad_category, dominant_age, dominant_gender, person_count)
    )
    conn.commit()
    conn.close()

def get_current_ad():
    """
    Returns the most recently selected ad category, plus the demographic
    info that triggered it. Falls back to 'default' if no selection has
    been logged yet (e.g. fresh database, or face analytics hasn't run).
    """
    conn = get_connection()
    row = conn.execute('''
        SELECT ad_category, dominant_age, dominant_gender, timestamp
        FROM ad_selections
        ORDER BY timestamp DESC
        LIMIT 1
    ''').fetchone()
    conn.close()

    if row is None:
        return {
            'ad_category': 'default',
            'dominant_age': None,
            'dominant_gender': None,
            'timestamp': None,
        }
    return dict(row)

def get_counts_last_hours(hours=24):
    conn = get_connection()
    rows = conn.execute('''
        SELECT timestamp, count FROM person_counts
        WHERE timestamp >= datetime('now', ? || ' hours')
        ORDER BY timestamp ASC
    ''', (f'-{hours}',)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_demographics_last_minutes(minutes=30):
    conn = get_connection()
    rows = conn.execute('''
        SELECT gender, age_group, COUNT(*) as count
        FROM face_events
        WHERE timestamp >= datetime('now', ? || ' minutes')
        GROUP BY gender, age_group
        ORDER BY count DESC
    ''', (f'-{minutes}',)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_avg_dwell_time():
    conn = get_connection()
    row = conn.execute('''
        SELECT AVG(duration) as avg_dwell
        FROM dwell_events
        WHERE duration > 0
        AND start_time >= datetime('now', '-24 hours')
    ''').fetchone()
    conn.close()
    return round(row['avg_dwell'] or 0, 2)


def get_dwell_summary(period='day', camera_id=None):
    """
    Returns average dwell duration (seconds) grouped by day/week/month.
    camera_id: filter to a specific camera (e.g. FACE_CAMERA_ID for
    "time spent in front of the demographic camera"); None = all cameras.
    """
    conn = get_connection()

    if period == 'day':
        group_expr = "date(start_time)"
        lookback   = "-30 days"
    elif period == 'week':
        group_expr = "strftime('%Y-W%W', start_time)"
        lookback   = "-90 days"
    elif period == 'month':
        group_expr = "strftime('%Y-%m', start_time)"
        lookback   = "-365 days"
    else:
        raise ValueError("period must be 'day', 'week', or 'month'")

    params = [lookback]
    cam_filter = ""
    if camera_id is not None:
        cam_filter = "AND camera_id = ?"
        params.append(camera_id)

    rows = conn.execute(f'''
        SELECT {group_expr} AS period_label,
               AVG(duration) AS avg_dwell,
               AVG(attentive_duration) AS avg_attentive_dwell
        FROM dwell_events
        WHERE duration > 0
        AND start_time >= datetime('now', ?)
        {cam_filter}
        GROUP BY period_label
        ORDER BY period_label ASC
    ''', params).fetchall()
    conn.close()

    return [
        {
            'period_label': r['period_label'],
            'avg_dwell': round(r['avg_dwell'] or 0, 2),
            'avg_attentive_dwell': round(r['avg_attentive_dwell'] or 0, 2),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Period summaries (day / week / month) — used for general analytics views
# ---------------------------------------------------------------------------

def get_traffic_summary(period='day'):
    """
    Returns a list of {period_label, total_count, avg_count, peak_count}
    rows, one per day/week/month, based on the person_counts table.

    period: 'day'   -> grouped by calendar day, last 30 days
            'week'  -> grouped by ISO week, last 12 weeks
            'month' -> grouped by calendar month, last 12 months
    """
    conn = get_connection()

    if period == 'day':
        group_expr = "date(timestamp)"
        lookback   = "-30 days"
    elif period == 'week':
        group_expr = "strftime('%Y-W%W', timestamp)"
        lookback   = "-90 days"
    elif period == 'month':
        group_expr = "strftime('%Y-%m', timestamp)"
        lookback   = "-365 days"
    else:
        raise ValueError("period must be 'day', 'week', or 'month'")

    rows = conn.execute(f'''
        SELECT {group_expr} AS period_label,
               SUM(count)   AS total_count,
               AVG(count)   AS avg_count,
               MAX(count)   AS peak_count
        FROM person_counts
        WHERE timestamp >= datetime('now', ?)
        GROUP BY period_label
        ORDER BY period_label ASC
    ''', (lookback,)).fetchall()
    conn.close()

    return [
        {
            'period_label': r['period_label'],
            'total_count':  r['total_count'] or 0,
            'avg_count':    round(r['avg_count'] or 0, 2),
            'peak_count':   r['peak_count'] or 0,
        }
        for r in rows
    ]


def get_demographics_summary(period='day'):
    """
    Returns demographic breakdown (gender + age_group counts) grouped by
    day/week/month, based on face_events.
    """
    conn = get_connection()

    if period == 'day':
        group_expr = "date(timestamp)"
        lookback   = "-30 days"
    elif period == 'week':
        group_expr = "strftime('%Y-W%W', timestamp)"
        lookback   = "-90 days"
    elif period == 'month':
        group_expr = "strftime('%Y-%m', timestamp)"
        lookback   = "-365 days"
    else:
        raise ValueError("period must be 'day', 'week', or 'month'")

    rows = conn.execute(f'''
        SELECT {group_expr} AS period_label,
               gender, age_group, COUNT(*) AS count
        FROM face_events
        WHERE timestamp >= datetime('now', ?)
        GROUP BY period_label, gender, age_group
        ORDER BY period_label ASC
    ''', (lookback,)).fetchall()
    conn.close()

    return [dict(r) for r in rows]


def get_hourly_traffic_pattern(days=30):
    """
    Returns average person count per hour-of-day over the last `days` days.
    Useful for "busiest hours" style charts.
    Result: list of 24 dicts {hour: 0-23, avg_count: float}
    """
    conn = get_connection()
    rows = conn.execute('''
        SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hour,
               AVG(count) AS avg_count
        FROM person_counts
        WHERE timestamp >= datetime('now', ? || ' days')
        GROUP BY hour
        ORDER BY hour ASC
    ''', (f'-{days}',)).fetchall()
    conn.close()

    by_hour = {r['hour']: round(r['avg_count'] or 0, 2) for r in rows}
    return [{'hour': h, 'avg_count': by_hour.get(h, 0)} for h in range(24)]


def get_unique_visitors(period='day'):
    """
    Returns unique visitor counts grouped by day/week/month, based on
    distinct object_id entries in tracking_events.
    NOTE: requires tracking_events to be populated (see log_tracking_event).
    """
    conn = get_connection()

    if period == 'day':
        group_expr = "date(first_seen)"
        lookback   = "-30 days"
    elif period == 'week':
        group_expr = "strftime('%Y-W%W', first_seen)"
        lookback   = "-90 days"
    elif period == 'month':
        group_expr = "strftime('%Y-%m', first_seen)"
        lookback   = "-365 days"
    else:
        raise ValueError("period must be 'day', 'week', or 'month'")

    rows = conn.execute(f'''
        SELECT {group_expr} AS period_label,
               COUNT(DISTINCT object_id) AS unique_visitors
        FROM tracking_events
        WHERE first_seen >= datetime('now', ?)
        GROUP BY period_label
        ORDER BY period_label ASC
    ''', (lookback,)).fetchall()
    conn.close()

    return [dict(r) for r in rows]


def get_attention_summary(period='day'):
    """
    Returns attention ratio (fraction of logged face_events where
    is_attentive=1) grouped by day/week/month. Combine with dwell time
    to estimate "attentive dwell time": avg_dwell * attention_ratio.
    """
    conn = get_connection()

    if period == 'day':
        group_expr = "date(timestamp)"
        lookback   = "-30 days"
    elif period == 'week':
        group_expr = "strftime('%Y-W%W', timestamp)"
        lookback   = "-90 days"
    elif period == 'month':
        group_expr = "strftime('%Y-%m', timestamp)"
        lookback   = "-365 days"
    else:
        raise ValueError("period must be 'day', 'week', or 'month'")

    rows = conn.execute(f'''
        SELECT {group_expr} AS period_label,
               AVG(is_attentive) AS attention_ratio,
               COUNT(*) AS sample_count
        FROM face_events
        WHERE timestamp >= datetime('now', ?)
        GROUP BY period_label
        ORDER BY period_label ASC
    ''', (lookback,)).fetchall()
    conn.close()

    return [
        {
            'period_label':    r['period_label'],
            'attention_ratio': round(r['attention_ratio'] or 0, 3),
            'sample_count':    r['sample_count'],
        }
        for r in rows
    ]


def log_tracking_event(object_id, first_seen, last_seen, camera_id=0):
    """Record a completed tracking session for unique-visitor counting."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO tracking_events (object_id, first_seen, last_seen, camera_id) VALUES (?,?,?,?)",
        (object_id, first_seen, last_seen, camera_id)
    )
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
