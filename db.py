import sqlite3
from datetime import datetime

DB_PATH = "bot_data.db"

# Заявки, оформленные раньше этой даты (релиз новой версии бота с этим функционалом),
# в еженедельный отчёт не попадают — они из старой версии бота и оформлены не по новому формату.
WEEKLY_REPORT_CUTOFF = datetime(2026, 7, 16, 23, 59, 59)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            language TEXT NOT NULL,
            server_type TEXT NOT NULL,
            area_size TEXT NOT NULL,
            vr_device TEXT,
            duration INTEGER NOT NULL,
            city TEXT NOT NULL,
            topic_id INTEGER NOT NULL,
            message_link TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        )
    ''')
    conn.commit()

    # Миграция: добавляем колонки, которых могло не быть в старой БД
    cursor.execute("PRAGMA table_info(requests)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    migrations = {
        "username": "ALTER TABLE requests ADD COLUMN username TEXT",
        "first_name": "ALTER TABLE requests ADD COLUMN first_name TEXT",
        "last_name": "ALTER TABLE requests ADD COLUMN last_name TEXT",
        "status": "ALTER TABLE requests ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        "reminded": "ALTER TABLE requests ADD COLUMN reminded INTEGER NOT NULL DEFAULT 0",
        "server_version": "ALTER TABLE requests ADD COLUMN server_version TEXT",
        "message_id": "ALTER TABLE requests ADD COLUMN message_id INTEGER",
        "original_text": "ALTER TABLE requests ADD COLUMN original_text TEXT",
        "build_link": "ALTER TABLE requests ADD COLUMN build_link TEXT",
        "pin_code": "ALTER TABLE requests ADD COLUMN pin_code TEXT",
        "calibration_plan": "ALTER TABLE requests ADD COLUMN calibration_plan TEXT",
        "demo_status": "ALTER TABLE requests ADD COLUMN demo_status TEXT",
    }
    for column, ddl in migrations.items():
        if column not in existing_columns:
            cursor.execute(ddl)
    conn.commit()
    conn.close()


def save_request(data, message_link: str, expires_at: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO requests (
            user_id, language, server_type, area_size, vr_device,
            duration, city, topic_id, message_link, expires_at,
            username, first_name, last_name, server_version,
            message_id, original_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data["user_id"], data["language"], data["server_type"], data["area_size"],
        data.get("vr_device"), data["duration"], data["city"],
        data["topic_id"], message_link, expires_at,
        data.get("username"), data.get("first_name"), data.get("last_name"),
        data.get("server_version"), data.get("message_id"), data.get("original_text")
    ))
    conn.commit()
    req_id = cursor.lastrowid
    conn.close()
    return req_id


def get_request_by_id(req_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM requests WHERE id = ?", (req_id,))
    columns = [d[0] for d in cursor.description]
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(zip(columns, row))
    return None


def get_requests_due_for_reminder(hours_before: int = 24):
    """Активные заявки, по которым ещё не напоминали и срок истекает
    в ближайшие hours_before часов (либо уже истёк)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM requests WHERE status = 'active' AND reminded = 0")
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()

    now = datetime.now()
    due = []
    for row in rows:
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
        hours_left = (expires_at - now).total_seconds() / 3600
        if hours_left <= hours_before:
            due.append(row)
    return due


def mark_reminded(req_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET reminded = 1 WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()


def extend_request(req_id: int, new_expires_at: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE requests SET expires_at = ?, reminded = 0 WHERE id = ?",
        (new_expires_at, req_id)
    )
    conn.commit()
    conn.close()


def close_request(req_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET status = 'closed' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()


def set_build_link(req_id: int, value: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET build_link = ? WHERE id = ?", (value, req_id))
    conn.commit()
    conn.close()


def set_pin_code(req_id: int, value: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET pin_code = ? WHERE id = ?", (value, req_id))
    conn.commit()
    conn.close()


def set_calibration_plan(req_id: int, value: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET calibration_plan = ? WHERE id = ?", (value, req_id))
    conn.commit()
    conn.close()


def set_demo_status(req_id: int, status: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET demo_status = ? WHERE id = ?", (status, req_id))
    conn.commit()
    conn.close()


def get_active_requests():
    """Заявки со статусом active, у которых срок демо ещё не истёк.
    Старые заявки, для которых никто не нажал "Отключить", но срок
    которых уже прошёл, в отчёт не попадают."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM requests WHERE status = 'active' ORDER BY topic_id, id")
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()

    now = datetime.now()
    result = []
    for row in rows:
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
        created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        if expires_at > now and created_at >= WEEKLY_REPORT_CUTOFF:
            result.append(row)
    return result
