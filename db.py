import sqlite3
from datetime import datetime, timedelta

DB_PATH = "bot_data.db"

# Заявки, оформленные раньше этой даты (релиз новой версии бота с этим функционалом),
# в еженедельный отчёт не попадают — они из старой версии бота и оформлены не по новому формату.
WEEKLY_REPORT_CUTOFF = datetime(2026, 7, 16, 23, 59, 59)

# Автоотключение по истечении срока и пинг техконтакта работают только для заявок,
# оформленных от этой даты — по старым заявкам таких уведомлений быть не должно.
AUTO_DISABLE_CUTOFF = datetime(2026, 8, 7, 0, 0, 0)

# Пинг о незавершённой настройке (нет PIN/билда) — тоже только для новых заявок,
# чтобы не поднимать разом все старые открытые заявки при первом деплое фичи.
SETUP_NUDGE_CUTOFF = datetime(2026, 9, 10, 0, 0, 0)


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
        "launcher_link": "ALTER TABLE requests ADD COLUMN launcher_link TEXT",
        "support_comment": "ALTER TABLE requests ADD COLUMN support_comment TEXT",
        "tech_contact_user_id": "ALTER TABLE requests ADD COLUMN tech_contact_user_id INTEGER",
        "tech_contact_first_name": "ALTER TABLE requests ADD COLUMN tech_contact_first_name TEXT",
        "tech_contact_last_name": "ALTER TABLE requests ADD COLUMN tech_contact_last_name TEXT",
        "disabled_at": "ALTER TABLE requests ADD COLUMN disabled_at TIMESTAMP",
        "reminder_message_id": "ALTER TABLE requests ADD COLUMN reminder_message_id INTEGER",
        "pin_code_prev": "ALTER TABLE requests ADD COLUMN pin_code_prev TEXT",
        "build_link_prev": "ALTER TABLE requests ADD COLUMN build_link_prev TEXT",
        "launcher_link_prev": "ALTER TABLE requests ADD COLUMN launcher_link_prev TEXT",
        "calibration_plan_prev": "ALTER TABLE requests ADD COLUMN calibration_plan_prev TEXT",
        "setup_reminded": "ALTER TABLE requests ADD COLUMN setup_reminded INTEGER NOT NULL DEFAULT 0",
        "area_size_prev": "ALTER TABLE requests ADD COLUMN area_size_prev TEXT",
        "expires_at_prev": "ALTER TABLE requests ADD COLUMN expires_at_prev TIMESTAMP",
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


def set_reminder_message_id(req_id: int, message_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET reminder_message_id = ? WHERE id = ?", (message_id, req_id))
    conn.commit()
    conn.close()


def update_message_location(req_id: int, message_id: int, message_link: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE requests SET message_id = ?, message_link = ? WHERE id = ?",
        (message_id, message_link, req_id)
    )
    conn.commit()
    conn.close()


def set_request_duration(req_id: int, duration: int, new_expires_at: str, prev_expires_at: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE requests SET duration = ?, expires_at = ?, expires_at_prev = ?, reminded = 0 WHERE id = ?",
        (duration, new_expires_at, prev_expires_at, req_id)
    )
    conn.commit()
    conn.close()


def set_vr_device(req_id: int, value: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET vr_device = ? WHERE id = ?", (value, req_id))
    conn.commit()
    conn.close()


def set_area_size(req_id: int, value: str, prev_value: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET area_size = ?, area_size_prev = ? WHERE id = ?", (value, prev_value, req_id))
    conn.commit()
    conn.close()


def set_server_version(req_id: int, value: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET server_version = ? WHERE id = ?", (value, req_id))
    conn.commit()
    conn.close()


def set_original_text(req_id: int, text: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET original_text = ? WHERE id = ?", (text, req_id))
    conn.commit()
    conn.close()


def close_request(req_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET status = 'closed' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()


def reactivate_request(req_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET status = 'active' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()


def set_build_link(req_id: int, value: str, prev_value: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET build_link = ?, build_link_prev = ? WHERE id = ?", (value, prev_value, req_id))
    conn.commit()
    conn.close()


def set_pin_code(req_id: int, value: str, prev_value: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET pin_code = ?, pin_code_prev = ? WHERE id = ?", (value, prev_value, req_id))
    conn.commit()
    conn.close()


def delete_request(req_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM requests WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()


def set_launcher_link(req_id: int, value: str, prev_value: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET launcher_link = ?, launcher_link_prev = ? WHERE id = ?", (value, prev_value, req_id))
    conn.commit()
    conn.close()


def set_support_comment(req_id: int, value: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET support_comment = ? WHERE id = ?", (value, req_id))
    conn.commit()
    conn.close()


def set_calibration_plan(req_id: int, value: str, prev_value: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE requests SET calibration_plan = ?, calibration_plan_prev = ? WHERE id = ?",
        (value, prev_value, req_id)
    )
    conn.commit()
    conn.close()


def set_demo_status(req_id: int, status: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if status == "disabled":
        # Запоминаем момент отключения — от него отсчитываются 2 недели до автоочистки.
        disabled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE requests SET demo_status = ?, disabled_at = ? WHERE id = ?",
            (status, disabled_at, req_id)
        )
    else:
        cursor.execute(
            "UPDATE requests SET demo_status = ?, disabled_at = NULL WHERE id = ?",
            (status, req_id)
        )
    conn.commit()
    conn.close()


def get_requests_to_auto_disable():
    """Заявки с истёкшим сроком демо, которые ещё не переведены (вручную или автоматически)
    в статус 'disabled' — их нужно закрыть и пропинговать техконтакта."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM requests WHERE (demo_status IS NULL OR demo_status != 'disabled') "
        "AND created_at >= ?",
        (AUTO_DISABLE_CUTOFF.strftime("%Y-%m-%d %H:%M:%S"),)
    )
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()

    now = datetime.now()
    due = []
    for row in rows:
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
        if expires_at <= now:
            due.append(row)
    return due


def get_requests_needing_setup_nudge(hours: int):
    """Активные заявки старше hours часов, для которых до сих пор не указан
    технический доступ (PIN для 1.3.0, ссылка на билд для остальных версий)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM requests WHERE status = 'active' AND setup_reminded = 0 AND created_at >= ?",
        (SETUP_NUDGE_CUTOFF.strftime("%Y-%m-%d %H:%M:%S"),)
    )
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()

    now = datetime.now()
    due = []
    for row in rows:
        created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        age_hours = (now - created_at).total_seconds() / 3600
        if age_hours < hours:
            continue
        if row.get("server_version") in ("1.3.0", "1.3.0.2"):
            missing = not row.get("pin_code")
        else:
            missing = not row.get("build_link")
        if missing:
            due.append(row)
    return due


def mark_setup_reminded(req_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET setup_reminded = 1 WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()


def get_requests_pending_cleanup(days: int = 14):
    """Заявки в статусе 'disabled' дольше указанного числа дней — подлежат удалению из БД."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM requests WHERE demo_status = 'disabled' AND disabled_at IS NOT NULL")
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()

    cutoff = datetime.now() - timedelta(days=days)
    stale = []
    for row in rows:
        disabled_at = datetime.strptime(row["disabled_at"], "%Y-%m-%d %H:%M:%S")
        if disabled_at <= cutoff:
            stale.append(row)
    return stale


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
        if row.get("demo_status") == "disabled":
            continue
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
        created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        if expires_at > now and created_at >= WEEKLY_REPORT_CUTOFF:
            result.append(row)
    return result
