import sqlite3
from datetime import datetime, date, timedelta
from io import BytesIO
import urllib.parse
import os

import pandas as pd
import qrcode
import streamlit as st

st.set_page_config(page_title="野田組 車両点検記録", page_icon="🚜", layout="wide")

APP_URL = "https://heavy-vehicle-check-ghka28mxhavp4qrjpnkb7b.streamlit.app"
ADMIN_CODE = "1224"
DB_PATH = "vehicle_check.db"
WEEK_JA = ["月", "火", "水", "木", "金", "土", "日"]

VEHICLE_TYPE_ALIASES = {
    "フォークリフト": "forklift",
    "forklift": "forklift",
    "FL": "forklift",
    "バックホウ": "backhoe",
    "バックホー": "backhoe",
    "backhoe": "backhoe",
    "BH": "backhoe",
    "ホイールローダー": "wheel_loader",
    "ホイールローダ": "wheel_loader",
    "wheel_loader": "wheel_loader",
    "wheelLoader": "wheel_loader",
    "WL": "wheel_loader",
    "ダンプ": "dump",
    "dump": "dump",
    "DP": "dump",
    "軽トラ": "light_truck",
    "軽トラック": "light_truck",
    "普通車": "light_truck",
    "light_truck": "light_truck",
    "LT": "light_truck",
    "車両": "vehicle",
    "vehicle": "vehicle",
    "重機": "construction",
    "construction": "construction",
    "その他": "other",
    "other": "other",
}

def clean_text(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    s = str(value)
    if s.lower() == "nan":
        return ""
    return s.replace("\\n", " ").replace("\n", " ").replace("\r", " ").strip()

def normalize_vehicle_type(value):
    v = clean_text(value)
    return VEHICLE_TYPE_ALIASES.get(v, v if v in VEHICLE_TYPE_ALIASES.values() else "other")

def safe_type_index(value, keys):
    vt = normalize_vehicle_type(value)
    try:
        return list(keys).index(vt)
    except Exception:
        return 0

def display_text(value):
    return clean_text(value)

DEFAULT_RETENTION_DAYS = 365

VEHICLE_TYPES = {
    "forklift": "フォークリフト",
    "backhoe": "バックホウ",
    "wheel_loader": "ホイールローダー",
    "dump": "ダンプ",
    "light_truck": "軽トラ・普通車",
    "vehicle": "車両",
    "construction": "重機",
    "other": "その他",
}

EDIT_TYPE_KEYS = ["forklift", "backhoe", "wheel_loader", "dump", "light_truck", "other"]

CHECK_ITEMS = {
    "forklift": [
        "制動装置・ブレーキ",
        "操縦装置・ハンドル・レバー",
        "フォーク・マスト・チェーン",
        "油圧装置・油漏れ",
        "タイヤ・ホイール",
        "ライト・警報装置・ホーン",
        "バッテリー・燃料",
    ],
    "backhoe": [
        "ブレーキ・走行装置",
        "操作レバー",
        "ブーム・アーム・バケット",
        "油圧ホース・油漏れ",
        "クローラ・足回り",
        "ライト・警報装置・ホーン",
        "エンジン・冷却水",
    ],
    "wheel_loader": [
        "ブレーキ・走行装置",
        "ステアリング",
        "バケット・リンク",
        "油圧装置・油漏れ",
        "タイヤ・ホイール",
        "ライト・警報装置・ホーン",
        "エンジン・冷却水",
    ],
    "dump": [
        "ブレーキ",
        "ハンドル",
        "タイヤ",
        "ライト・ウインカー",
        "ホーン",
        "荷台・ダンプ機構",
        "油漏れ・水漏れ",
        "エンジン",
    ],
    "light_truck": [
        "ブレーキ",
        "ハンドル",
        "タイヤ",
        "ライト・ウインカー",
        "ホーン",
        "エンジンオイル",
        "冷却水",
        "荷台・車体外観",
    ],
    "vehicle": [
        "ブレーキ",
        "ハンドル",
        "タイヤ",
        "ライト・ウインカー",
        "ホーン",
        "油漏れ・水漏れ",
        "車体外観",
    ],
    "construction": [
        "ブレーキ・走行装置",
        "操作装置",
        "作業装置・油圧装置",
        "足回り・外観",
        "ライト・警報装置・ホーン",
        "エンジン・冷却水",
    ],
    "other": [
        "ブレーキ・操作装置",
        "作業装置・油圧装置",
        "足回り・外観",
        "ライト・警報装置・ホーン",
        "油漏れ・水漏れ",
    ],
}

def ja_date(d):
    if not d:
        return ""
    return f"{d.year}年{d.month}月{d.day}日（{WEEK_JA[d.weekday()]}）"

def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def ensure_column(cur, table, column, definition):
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    con = connect()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            vehicle_no TEXT PRIMARY KEY,
            vehicle_name TEXT NOT NULL,
            vehicle_type TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            use_locked INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    ensure_column(cur, "vehicles", "next_inspection_date", "TEXT")
    ensure_column(cur, "vehicles", "note", "TEXT")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspected_at TEXT NOT NULL,
            inspection_date TEXT NOT NULL,
            vehicle_no TEXT NOT NULL,
            vehicle_name TEXT NOT NULL,
            vehicle_type TEXT NOT NULL,
            inspector TEXT NOT NULL,
            meter TEXT,
            result TEXT NOT NULL,
            abnormal_detail TEXT,
            action_detail TEXT,
            photo_name TEXT,
            photo_bytes BLOB,
            photo2_name TEXT,
            photo2_bytes BLOB,
            photo3_name TEXT,
            photo3_bytes BLOB,
            photo4_name TEXT,
            photo4_bytes BLOB,
            manager_confirmed INTEGER DEFAULT 0,
            manager_name TEXT,
            manager_confirmed_at TEXT
        )
    """)
    for col, typ in [
        ("photo2_name", "TEXT"), ("photo2_bytes", "BLOB"),
        ("photo3_name", "TEXT"), ("photo3_bytes", "BLOB"),
        ("photo4_name", "TEXT"), ("photo4_bytes", "BLOB"),
    ]:
        ensure_column(cur, "inspections", col, typ)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspection_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspector_name TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1,
            note TEXT,
            cert1_name TEXT,
            cert1_bytes BLOB,
            cert2_name TEXT,
            cert2_bytes BLOB,
            cert3_name TEXT,
            cert3_bytes BLOB,
            cert4_name TEXT,
            cert4_bytes BLOB,
            created_at TEXT NOT NULL
        )
    """)

    con.commit()
    con.close()

def normalize_old_vehicle_types():
    # 古い版で登録された vehicle / construction も残して動くが、編集時に新区分へ直せる
    pass

def seed_vehicles():
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM vehicles")
    if cur.fetchone()[0] == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        next_d = (date.today() + timedelta(days=30)).isoformat()
        rows = [
            ("FL-001", "フォークリフト1号", "forklift"),
            ("BH-001", "バックホウ1号", "backhoe"),
            ("WL-001", "ホイールローダー1号", "wheel_loader"),
            ("DP-001", "ダンプ1号", "dump"),
            ("LT-001", "軽トラ1号", "light_truck"),
        ]
        for no, name, typ in rows:
            cur.execute(
                """INSERT INTO vehicles(
                    vehicle_no, vehicle_name, vehicle_type, active, use_locked, created_at, next_inspection_date, note
                ) VALUES (?, ?, ?, 1, 0, ?, ?, '')""",
                (no, name, typ, now, next_d)
            )
    con.commit()
    con.close()


def repair_vehicle_master_data():
    con = connect()
    cur = con.cursor()
    try:
        cur.execute("SELECT vehicle_no, vehicle_name, vehicle_type, note FROM vehicles")
        rows = cur.fetchall()
        for old_no, old_name, old_type, old_note in rows:
            new_no = clean_text(old_no)
            new_name = clean_text(old_name)
            new_type = normalize_vehicle_type(old_type)
            new_note = clean_text(old_note)

            # 空番号は触らず無効化
            if not new_no:
                cur.execute("UPDATE vehicles SET active=0, note=? WHERE vehicle_no=?", ("車両番号が空のため無効化", old_no))
                continue

            # Primary key changeは衝突時を考慮
            if new_no != old_no:
                cur.execute("SELECT COUNT(*) FROM vehicles WHERE vehicle_no=?", (new_no,))
                exists = cur.fetchone()[0]
                if exists:
                    cur.execute("UPDATE vehicles SET active=0, note=? WHERE vehicle_no=?", ("重複または文字化けのため無効化", old_no))
                    continue
                cur.execute(
                    "UPDATE vehicles SET vehicle_no=?, vehicle_name=?, vehicle_type=?, note=? WHERE vehicle_no=?",
                    (new_no, new_name, new_type, new_note, old_no)
                )
            else:
                cur.execute(
                    "UPDATE vehicles SET vehicle_name=?, vehicle_type=?, note=? WHERE vehicle_no=?",
                    (new_name, new_type, new_note, old_no)
                )

        # 点検履歴側も表示用に補正
        cur.execute("SELECT id, vehicle_no, vehicle_name, vehicle_type, inspector, meter, abnormal_detail, action_detail FROM inspections")
        logs = cur.fetchall()
        for row in logs:
            log_id, vno, vname, vtype, inspector, meter, abnormal, action = row
            cur.execute(
                """UPDATE inspections
                   SET vehicle_no=?, vehicle_name=?, vehicle_type=?, inspector=?, meter=?, abnormal_detail=?, action_detail=?
                   WHERE id=?""",
                (
                    clean_text(vno),
                    clean_text(vname),
                    normalize_vehicle_type(vtype),
                    clean_text(inspector),
                    clean_text(meter),
                    clean_text(abnormal),
                    clean_text(action),
                    log_id,
                )
            )

        con.commit()
    finally:
        con.close()


def get_vehicles(active_only=True):
    con = connect()
    sql = "SELECT * FROM vehicles"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY vehicle_no"
    df = pd.read_sql_query(sql, con)
    con.close()
    if not df.empty:
        for col in ["vehicle_no", "vehicle_name", "vehicle_type", "note", "inspector", "meter", "abnormal_detail", "action_detail"]:
            if col in df.columns:
                df[col] = df[col].apply(clean_text)
        if "vehicle_type" in df.columns:
            df["vehicle_type"] = df["vehicle_type"].apply(normalize_vehicle_type)
    return df

def get_vehicle(vehicle_no):
    con = connect()
    df = pd.read_sql_query("SELECT * FROM vehicles WHERE vehicle_no = ?", con, params=(vehicle_no,))
    con.close()
    if df.empty:
        return None
    return df.iloc[0].to_dict()

def add_vehicle(no, name, typ, next_d, note):
    con = connect()
    try:
        con.execute(
            """INSERT INTO vehicles(
                vehicle_no, vehicle_name, vehicle_type, active, use_locked, created_at, next_inspection_date, note
            ) VALUES (?, ?, ?, 1, 0, ?, ?, ?)""",
            (clean_text(no), clean_text(name), normalize_vehicle_type(typ), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), next_d.isoformat(), clean_text(note))
        )
        con.commit()
        return True, "車両を登録しました。"
    except sqlite3.IntegrityError:
        return False, "同じ車両番号が既にあります。"
    finally:
        con.close()

def update_vehicle(no, name, typ, active, next_d, note):
    con = connect()
    con.execute(
        """UPDATE vehicles
           SET vehicle_name = ?, vehicle_type = ?, active = ?, next_inspection_date = ?, note = ?
           WHERE vehicle_no = ?""",
        (clean_text(name), normalize_vehicle_type(typ), 1 if active else 0, next_d.isoformat(), clean_text(note), clean_text(no))
    )
    con.commit()
    con.close()

def delete_vehicle(no):
    con = connect()
    con.execute("DELETE FROM vehicles WHERE vehicle_no = ?", (no,))
    con.commit()
    con.close()


def force_delete_vehicle(no):
    no = clean_text(no)
    con = connect()
    cur = con.cursor()
    cur.execute("DELETE FROM vehicles WHERE vehicle_no=?", (no,))
    deleted = cur.rowcount
    con.commit()
    con.close()
    return deleted

def reset_vehicle_lock(no):
    con = connect()
    con.execute("UPDATE vehicles SET use_locked = 0 WHERE vehicle_no = ?", (no,))
    con.commit()
    con.close()

def save_inspection(vehicle, inspection_date, inspector, meter, statuses, abnormal_detail, action_detail, photos):
    has_abnormal = any(v == "異常あり" for v in statuses.values())
    result = "使用不可" if has_abnormal else "使用可"

    photo_data = []
    for p in (photos or [])[:4]:
        photo_data.append((p.name, p.getvalue()))
    while len(photo_data) < 4:
        photo_data.append(("", None))

    con = connect()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO inspections(
            inspected_at, inspection_date, vehicle_no, vehicle_name, vehicle_type,
            inspector, meter, result, abnormal_detail, action_detail,
            photo_name, photo_bytes, photo2_name, photo2_bytes, photo3_name, photo3_bytes, photo4_name, photo4_bytes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        inspection_date.isoformat(),
        vehicle["vehicle_no"], vehicle["vehicle_name"], vehicle["vehicle_type"],
        inspector, meter, result, abnormal_detail, action_detail,
        photo_data[0][0], photo_data[0][1],
        photo_data[1][0], photo_data[1][1],
        photo_data[2][0], photo_data[2][1],
        photo_data[3][0], photo_data[3][1],
    ))
    inspection_id = cur.lastrowid

    for item, status in statuses.items():
        cur.execute(
            "INSERT INTO inspection_items(inspection_id, item_name, status) VALUES (?, ?, ?)",
            (inspection_id, item, status)
        )

    if has_abnormal:
        cur.execute("UPDATE vehicles SET use_locked = 1 WHERE vehicle_no = ?", (vehicle["vehicle_no"],))

    con.commit()
    con.close()

def get_inspections(where="", params=()):
    con = connect()
    sql = "SELECT * FROM inspections"
    if where:
        sql += " WHERE " + where
    sql += " ORDER BY inspection_date DESC, inspected_at DESC"
    df = pd.read_sql_query(sql, con, params=params)
    con.close()
    return df


def get_today_inspection(vehicle_no):
    df = get_inspections(
        "vehicle_no = ? AND inspection_date = ?",
        (vehicle_no, date.today().isoformat())
    )
    if df.empty:
        return None
    return df.iloc[0]

def get_items(inspection_id):
    con = connect()
    df = pd.read_sql_query(
        "SELECT item_name, status FROM inspection_items WHERE inspection_id = ?",
        con,
        params=(inspection_id,)
    )
    con.close()
    return df

def confirm_inspection(inspection_id, vehicle_no, manager_name):
    con = connect()
    con.execute(
        """UPDATE inspections
           SET manager_confirmed = 1, manager_name = ?, manager_confirmed_at = ?
           WHERE id = ?""",
        (manager_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inspection_id)
    )
    con.execute("UPDATE vehicles SET use_locked = 0 WHERE vehicle_no = ?", (vehicle_no,))
    con.commit()
    con.close()

def update_inspection_date(inspection_id, new_date):
    con = connect()
    con.execute("UPDATE inspections SET inspection_date = ? WHERE id = ?", (new_date.isoformat(), inspection_id))
    con.commit()
    con.close()

def delete_logs(start_date, end_date):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT id FROM inspections WHERE inspection_date BETWEEN ? AND ?", (start_date.isoformat(), end_date.isoformat()))
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        cur.execute(f"DELETE FROM inspection_items WHERE inspection_id IN ({placeholders})", ids)
        cur.execute(f"DELETE FROM inspections WHERE id IN ({placeholders})", ids)
    con.commit()
    con.close()
    return len(ids)

def delete_logs_older_than(cutoff_date):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT id FROM inspections WHERE inspection_date < ?", (cutoff_date.isoformat(),))
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        cur.execute(f"DELETE FROM inspection_items WHERE inspection_id IN ({placeholders})", ids)
        cur.execute(f"DELETE FROM inspections WHERE id IN ({placeholders})", ids)
    con.commit()
    con.close()
    return len(ids)


def get_inspectors(active_only=True):
    con = connect()
    sql = "SELECT * FROM inspectors"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY inspector_name"
    df = pd.read_sql_query(sql, con)
    con.close()
    return df

def add_inspector(inspector_name, note, certs):
    cert_data = []
    for c in (certs or [])[:4]:
        cert_data.append((c.name, c.getvalue()))
    while len(cert_data) < 4:
        cert_data.append(("", None))

    con = connect()
    try:
        con.execute(
            """INSERT INTO inspectors(
                inspector_name, active, note,
                cert1_name, cert1_bytes, cert2_name, cert2_bytes,
                cert3_name, cert3_bytes, cert4_name, cert4_bytes,
                created_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                inspector_name.strip(), note,
                cert_data[0][0], cert_data[0][1],
                cert_data[1][0], cert_data[1][1],
                cert_data[2][0], cert_data[2][1],
                cert_data[3][0], cert_data[3][1],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        con.commit()
        return True, "点検者を登録しました。"
    except sqlite3.IntegrityError:
        return False, "同じ点検者名が既にあります。"
    finally:
        con.close()

def update_inspector(inspector_id, inspector_name, active, note, certs, replace_certs):
    con = connect()
    if replace_certs:
        cert_data = []
        for c in (certs or [])[:4]:
            cert_data.append((c.name, c.getvalue()))
        while len(cert_data) < 4:
            cert_data.append(("", None))
        con.execute(
            """UPDATE inspectors
               SET inspector_name=?, active=?, note=?,
                   cert1_name=?, cert1_bytes=?,
                   cert2_name=?, cert2_bytes=?,
                   cert3_name=?, cert3_bytes=?,
                   cert4_name=?, cert4_bytes=?
               WHERE id=?""",
            (
                inspector_name.strip(), 1 if active else 0, note,
                cert_data[0][0], cert_data[0][1],
                cert_data[1][0], cert_data[1][1],
                cert_data[2][0], cert_data[2][1],
                cert_data[3][0], cert_data[3][1],
                inspector_id,
            )
        )
    else:
        con.execute(
            "UPDATE inspectors SET inspector_name=?, active=?, note=? WHERE id=?",
            (inspector_name.strip(), 1 if active else 0, note, inspector_id)
        )
    con.commit()
    con.close()

def delete_inspector(inspector_id):
    con = connect()
    con.execute("DELETE FROM inspectors WHERE id=?", (inspector_id,))
    con.commit()
    con.close()

def render_certs(row, width=160):
    pairs = [
        ("cert1_name", "cert1_bytes"),
        ("cert2_name", "cert2_bytes"),
        ("cert3_name", "cert3_bytes"),
        ("cert4_name", "cert4_bytes"),
    ]
    cols = st.columns(4)
    shown = False
    for i, (name_col, bytes_col) in enumerate(pairs):
        if bytes_col in row.index and row[bytes_col] is not None:
            with cols[i]:
                st.image(row[bytes_col], caption=row.get(name_col, ""), width=width)
            shown = True
    if not shown:
        st.caption("資格者証未添付")


def make_qr_png(url):
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def qr_url(vehicle_no):
    return APP_URL.rstrip("/") + "/?vehicle=" + urllib.parse.quote(str(vehicle_no), safe="")

def admin_url():
    return APP_URL.rstrip("/") + "/?admin=true"

def get_query_value(key):
    try:
        v = st.query_params.get(key, "")
    except Exception:
        return ""
    if isinstance(v, list):
        v = v[0] if v else ""
    return urllib.parse.unquote(str(v or ""))

def parse_iso_date(v):
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        return None

def render_photos(row, width=160):
    pairs = [
        ("photo_name", "photo_bytes"),
        ("photo2_name", "photo2_bytes"),
        ("photo3_name", "photo3_bytes"),
        ("photo4_name", "photo4_bytes"),
    ]
    cols = st.columns(4)
    shown = False
    for i, (name_col, bytes_col) in enumerate(pairs):
        if bytes_col in row.index and row[bytes_col] is not None:
            with cols[i]:
                st.image(row[bytes_col], caption=row.get(name_col, ""), width=width)
            shown = True
    if not shown:
        st.caption("写真なし")

def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")

def require_admin():
    if "admin_ok" not in st.session_state:
        st.session_state.admin_ok = False
    if st.session_state.admin_ok:
        return True

    st.markdown("### 管理者認証")
    code = st.text_input("管理者コード", type="password")
    if st.button("認証"):
        if code == ADMIN_CODE:
            st.session_state.admin_ok = True
            st.success("認証しました。")
            st.rerun()
        else:
            st.error("管理者コードが違います。")
    return False


def system_error_checks():
    errors = []
    warnings = []

    vehicles = get_vehicles(active_only=True)
    all_vehicles = get_vehicles(active_only=False)
    inspectors = get_inspectors(active_only=True) if "get_inspectors" in globals() else pd.DataFrame()
    abnormal = get_inspections("result = ?", ("使用不可",))
    today_logs = get_inspections("inspection_date = ?", (date.today().isoformat(),))

    if all_vehicles.empty:
        errors.append("車両マスターが未登録です。")
    elif vehicles.empty:
        errors.append("有効な車両がありません。")

    if inspectors.empty:
        warnings.append("有効な点検者が登録されていません。点検者マスターを登録してください。")

    if not inspectors.empty:
        no_cert = 0
        for _, r in inspectors.iterrows():
            if ("cert1_bytes" in r.index and r["cert1_bytes"] is None and
                "cert2_bytes" in r.index and r["cert2_bytes"] is None and
                "cert3_bytes" in r.index and r["cert3_bytes"] is None and
                "cert4_bytes" in r.index and r["cert4_bytes"] is None):
                no_cert += 1
        if no_cert > 0:
            warnings.append(f"資格者証未添付の点検者が{no_cert}名います。")

    if not vehicles.empty:
        locked = vehicles[vehicles["use_locked"] == 1]
        if len(locked) > 0:
            errors.append(f"使用禁止中の車両が{len(locked)}台あります。")

    if not abnormal.empty:
        unconfirmed = abnormal[abnormal["manager_confirmed"] == 0]
        if len(unconfirmed) > 0:
            errors.append(f"未承認の異常記録が{len(unconfirmed)}件あります。")

    unchecked = today_unchecked()
    if len(unchecked) > 0:
        warnings.append(f"本日未点検の車両が{len(unchecked)}台あります。")

    cutoff = date.today() - timedelta(days=365)
    old_logs = get_inspections("inspection_date < ?", (cutoff.isoformat(),))
    if len(old_logs) > 0:
        warnings.append(f"1年を超過したログが{len(old_logs)}件あります。ログ整理を推奨します。")

    try:
        db_size = os.path.getsize(DB_PATH)
        if db_size > 200 * 1024 * 1024:
            warnings.append("データベース容量が200MBを超えています。Excel出力後のログ整理を推奨します。")
    except Exception:
        pass

    return errors, warnings

def render_system_status():
    errors, warnings = system_error_checks()

    st.markdown("### システム状態")
    c1, c2 = st.columns(2)
    c1.metric("要対応", len(errors))
    c2.metric("注意", len(warnings))

    if not errors and not warnings:
        st.success("現在、重大な未対応・設定不備は検知されていません。")
    else:
        for e in errors:
            st.error(e)
        for w in warnings:
            st.warning(w)


def today_unchecked():
    vehicles = get_vehicles(True)
    checked = get_inspections("inspection_date = ?", (date.today().isoformat(),))
    checked_set = set(checked["vehicle_no"].tolist()) if not checked.empty else set()
    if vehicles.empty:
        return pd.DataFrame()
    return vehicles[~vehicles["vehicle_no"].isin(checked_set)]

def inspection_alerts():
    df = get_vehicles(active_only=True)
    if df.empty or "next_inspection_date" not in df.columns:
        return pd.DataFrame()
    rows = []
    for _, r in df.iterrows():
        d = parse_iso_date(r.get("next_inspection_date", ""))
        if d:
            days = (d - date.today()).days
            if days <= 7:
                rows.append({
                    "車両番号": r["vehicle_no"],
                    "車両名": r["vehicle_name"],
                    "次回点検日": ja_date(d),
                    "残日数": days,
                    "状態": "期限切れ" if days < 0 else "間近",
                })
    return pd.DataFrame(rows)

def make_export_df(df):
    export_df = df.drop(columns=["photo_bytes", "photo2_bytes", "photo3_bytes", "photo4_bytes"], errors="ignore").copy()
    export_df = export_df.rename(columns={
        "id": "ID",
        "inspected_at": "保存日時",
        "inspection_date": "点検日",
        "vehicle_no": "車両番号",
        "vehicle_name": "車両名",
        "vehicle_type": "区分",
        "inspector": "点検者",
        "meter": "メーター",
        "result": "判定",
        "abnormal_detail": "異常内容",
        "action_detail": "対応内容",
        "photo_name": "写真1",
        "photo2_name": "写真2",
        "photo3_name": "写真3",
        "photo4_name": "写真4",
        "manager_confirmed": "管理者確認",
        "manager_name": "管理者名",
        "manager_confirmed_at": "管理者確認日時",
    })
    if "区分" in export_df.columns:
        mapped = export_df["区分"].map(VEHICLE_TYPES)
        export_df["区分"] = mapped.fillna(export_df["区分"])
    if "管理者確認" in export_df.columns:
        export_df["管理者確認"] = export_df["管理者確認"].apply(lambda x: "確認済" if x else "未確認")

    item_texts = []
    for _, row in df.iterrows():
        items = get_items(row["id"])
        item_texts.append(" / ".join([f"{r['item_name']}:{r['status']}" for _, r in items.iterrows()]))
    export_df["点検項目"] = item_texts
    return export_df

def excel_bytes(export_df):
    excel_buf = BytesIO()

    with pd.ExcelWriter(excel_buf, engine="xlsxwriter") as writer:
        workbook = writer.book

        title_fmt = workbook.add_format({
            "bold": True, "font_size": 18, "align": "center", "valign": "vcenter",
            "fg_color": "#1F4E78", "font_color": "white"
        })
        sub_fmt = workbook.add_format({
            "font_size": 11, "align": "left", "valign": "vcenter"
        })
        header_fmt = workbook.add_format({
            "bold": True, "font_color": "white", "fg_color": "#305496",
            "border": 1, "align": "center", "valign": "vcenter"
        })
        cell_fmt = workbook.add_format({
            "border": 1, "valign": "top", "text_wrap": True
        })
        date_fmt = workbook.add_format({
            "border": 1, "valign": "top", "num_format": "yyyy/mm/dd"
        })
        ok_fmt = workbook.add_format({
            "border": 1, "valign": "top", "fg_color": "#E2F0D9", "font_color": "#375623"
        })
        ng_fmt = workbook.add_format({
            "border": 1, "valign": "top", "fg_color": "#FCE4D6", "font_color": "#9C0006"
        })
        summary_header_fmt = workbook.add_format({
            "bold": True, "font_color": "white", "fg_color": "#548235",
            "border": 1, "align": "center"
        })
        summary_cell_fmt = workbook.add_format({
            "border": 1, "align": "center"
        })

        # 表紙
        cover = workbook.add_worksheet("表紙")
        cover.merge_range("A1:H2", "野田組 車両点検記録", title_fmt)
        cover.write("A4", "出力日時", sub_fmt)
        cover.write("B4", datetime.now().strftime("%Y/%m/%d %H:%M"), sub_fmt)
        cover.write("A5", "出力件数", sub_fmt)
        cover.write("B5", len(export_df), sub_fmt)
        cover.write("A7", "内容", sub_fmt)
        cover.write("B7", "点検履歴・異常記録・管理者確認状況", sub_fmt)
        cover.set_column("A:A", 14)
        cover.set_column("B:H", 22)

        # 集計
        summary = workbook.add_worksheet("集計")
        summary.merge_range("A1:F1", "点検集計", title_fmt)

        if len(export_df) > 0:
            summary_df = export_df.copy()
            if "車両番号" in summary_df.columns and "判定" in summary_df.columns:
                pivot = pd.pivot_table(
                    summary_df,
                    index=["車両番号", "車両名"] if "車両名" in summary_df.columns else ["車両番号"],
                    columns="判定",
                    values="ID" if "ID" in summary_df.columns else summary_df.columns[0],
                    aggfunc="count",
                    fill_value=0
                ).reset_index()
                pivot.columns = [str(c) for c in pivot.columns]
            else:
                pivot = pd.DataFrame({"件数": [len(summary_df)]})
        else:
            pivot = pd.DataFrame({"件数": [0]})

        start_row = 3
        for col_idx, col_name in enumerate(pivot.columns):
            summary.write(start_row, col_idx, col_name, summary_header_fmt)
        for r_idx, (_, row) in enumerate(pivot.iterrows(), start=start_row + 1):
            for c_idx, value in enumerate(row):
                summary.write(r_idx, c_idx, value, summary_cell_fmt)
        summary.set_column(0, max(len(pivot.columns) - 1, 0), 18)
        summary.freeze_panes(start_row + 1, 0)

        # 点検履歴
        sheet_name = "点検履歴"
        export_df.to_excel(writer, index=False, sheet_name=sheet_name, startrow=3)
        ws = writer.sheets[sheet_name]

        max_row = len(export_df)
        max_col = len(export_df.columns)

        if max_col > 0:
            ws.merge_range(0, 0, 1, max_col - 1, "野田組 車両点検記録 一覧表", title_fmt)
            ws.write(2, 0, f"出力日時：{datetime.now().strftime('%Y/%m/%d %H:%M')}", sub_fmt)

            for col_idx, col_name in enumerate(export_df.columns):
                ws.write(3, col_idx, col_name, header_fmt)

            for row_idx in range(max_row):
                for col_idx, col_name in enumerate(export_df.columns):
                    value = export_df.iloc[row_idx, col_idx]
                    fmt = cell_fmt
                    if col_name == "点検日":
                        fmt = date_fmt
                    if col_name == "判定":
                        if str(value) == "使用不可":
                            fmt = ng_fmt
                        elif str(value) == "使用可":
                            fmt = ok_fmt
                    ws.write(row_idx + 4, col_idx, "" if pd.isna(value) else value, fmt)

            ws.freeze_panes(4, 0)
            ws.autofilter(3, 0, max_row + 3, max_col - 1)

            widths = {
                "ID": 8,
                "保存日時": 18,
                "点検日": 14,
                "車両番号": 14,
                "車両名": 22,
                "区分": 14,
                "点検者": 14,
                "メーター": 18,
                "判定": 12,
                "異常内容": 34,
                "対応内容": 34,
                "写真1": 22,
                "写真2": 22,
                "写真3": 22,
                "写真4": 22,
                "管理者確認": 14,
                "管理者名": 14,
                "管理者確認日時": 18,
                "点検項目": 48,
            }
            for col_idx, col_name in enumerate(export_df.columns):
                width = widths.get(col_name, 16)
                ws.set_column(col_idx, col_idx, width)

            ws.set_landscape()
            ws.fit_to_pages(1, 0)
            ws.set_margins(left=0.3, right=0.3, top=0.6, bottom=0.6)
            ws.repeat_rows(0, 3)

    return excel_buf.getvalue()

init_db()
seed_vehicles()
repair_vehicle_master_data()

st.markdown("""
<style>
.block-container {padding-top: 1rem; max-width: 1120px;}
div.stButton > button {border-radius: 10px; font-weight: 700;}
h1,h2,h3 {line-height: 1.25;}
@media print {
  section[data-testid="stSidebar"], header, footer, .stButton {display:none !important;}
}
</style>
""", unsafe_allow_html=True)

st.title("🚜 野田組 車両点検記録")
st.caption("日常点検・運行前点検記録システム")

query_vehicle = get_query_value("vehicle")
query_admin = get_query_value("admin") == "true"

vehicles_now = get_vehicles(True)
valid_nos = set(vehicles_now["vehicle_no"].tolist()) if not vehicles_now.empty else set()
if query_vehicle and query_vehicle not in valid_nos:
    st.warning("QRコードの車両番号が車両マスターにありません。車両を選択してください。")
    query_vehicle = ""

if query_vehicle:
    st.success(f"QRコードから車両を固定しました：{query_vehicle}")

alerts = inspection_alerts()
if not alerts.empty:
    st.warning("次回点検日が近い、または期限切れの車両があります。")
    st.table(alerts)

menu_options = ["点検入力", "管理者メニュー", "車両削除", "エラー検知", "異常一覧", "履歴・出力", "ログ整理", "車両マスター", "点検者マスター", "QRコード発行", "QR印刷台紙"]
default_menu = "管理者メニュー" if query_admin else "点検入力"
menu = st.sidebar.radio("メニュー", menu_options, index=menu_options.index(default_menu))

if menu == "点検入力":
    st.markdown("## 点検入力")
    vehicles = get_vehicles(True)
    if vehicles.empty:
        st.warning("車両マスターに車両を登録してください。")
        st.stop()

    options = vehicles["vehicle_no"].tolist()
    if query_vehicle and query_vehicle in options:
        selected_no = query_vehicle
        name = vehicles.loc[vehicles["vehicle_no"] == selected_no, "vehicle_name"].iloc[0]
        st.info(f"車両固定：{selected_no} / {name}")
    else:
        selected_no = st.selectbox(
            "車両",
            options,
            format_func=lambda no: f"{display_text(no)} / {display_text(vehicles.loc[vehicles['vehicle_no'] == no, 'vehicle_name'].iloc[0])}"
        )

    vehicle = get_vehicle(selected_no)
    vehicle_type = normalize_vehicle_type(vehicle["vehicle_type"])

    c1, c2, c3 = st.columns(3)
    c1.metric("車両番号", display_text(vehicle["vehicle_no"]))
    c2.metric("車両名", display_text(vehicle["vehicle_name"]))
    c3.metric("区分", VEHICLE_TYPES.get(normalize_vehicle_type(vehicle_type), normalize_vehicle_type(vehicle_type)))

    today_done = get_today_inspection(selected_no)
    if today_done is not None:
        if query_vehicle and selected_no == query_vehicle:
            st.success("本日の日常点検は完了しています。")
            st.write(f"点検者：{today_done['inspector']}")
            st.write(f"保存日時：{today_done['inspected_at']}")
            if today_done["result"] == "使用不可":
                st.error("判定：使用不可")
            else:
                st.success("判定：使用可")
            with st.expander("本日の点検内容を確認"):
                if today_done.get("meter"):
                    st.write(f"メーター：{today_done['meter']}")
                if today_done.get("abnormal_detail"):
                    st.write(f"異常内容：{today_done['abnormal_detail']}")
                if today_done.get("action_detail"):
                    st.write(f"対応内容：{today_done['action_detail']}")
                items_df = get_items(today_done["id"]).rename(columns={"item_name": "点検項目", "status": "判定"})
                st.table(items_df)
                render_photos(today_done)
            force_recheck = st.checkbox("再点検として新しく記録する")
            if not force_recheck:
                st.info("再点検する場合だけチェックを入れてください。")
                st.stop()
        else:
            st.info("この車両は本日すでに点検済みです。必要なら再点検として保存できます。")

    inspection_date = st.date_input("点検日", value=date.today())
    st.caption(f"点検日：{ja_date(inspection_date)}")

    if vehicle.get("use_locked", 0):
        st.error("この車両は異常報告により使用禁止中です。管理者確認まで使用しないでください。")

    inspectors_df = get_inspectors(active_only=True)
    if inspectors_df.empty:
        inspector = st.text_input("点検者名", placeholder="氏名")
        st.caption("点検者マスター未登録のため手入力です。")
    else:
        inspector = st.selectbox("点検者", inspectors_df["inspector_name"].tolist())
    meter = st.text_input("メーター・走行距離・アワーメーター", placeholder="例：1234h / 56000km")

    st.markdown("### 点検項目")
    statuses = {}
    for i, item in enumerate(CHECK_ITEMS.get(vehicle_type, CHECK_ITEMS["other"])):
        with st.container(border=True):
            st.markdown(f"**{item}**")
            statuses[item] = st.radio("判定", ["良好", "異常あり", "対象外"], horizontal=True, key=f"{selected_no}_{i}_{item}")

    has_abnormal = any(v == "異常あり" for v in statuses.values())
    abnormal_detail = ""
    action_detail = ""
    photos = []

    if has_abnormal:
        st.error("異常あり：この車両は使用不可として保存されます。")
        abnormal_detail = st.text_area("異常内容 ※必須", placeholder="どこが、どう悪いか")
        action_detail = st.text_area("対応内容 ※必須", placeholder="使用停止、修理依頼、管理者報告など")
        photos = st.file_uploader("写真添付 ※必須・最大4枚", type=["jpg", "jpeg", "png", "webp", "heic"], accept_multiple_files=True)
        if photos and len(photos) > 4:
            st.warning("写真は最大4枚までです。先頭4枚だけ保存します。")
            photos = photos[:4]

    if has_abnormal:
        st.error("最終判定：使用不可")
    else:
        st.success("最終判定：使用可")

    same_day_existing = get_today_inspection(selected_no)
    if same_day_existing is not None and not (query_vehicle and selected_no == query_vehicle):
        st.warning("この車両は本日すでに点検済みです。重複登録に注意してください。")

    if st.button("点検記録を保存", type="primary", use_container_width=True):
        if not inspector:
            st.warning("点検者名を入力してください。")
        elif has_abnormal and (not abnormal_detail or not action_detail or not photos):
            st.warning("異常ありの場合は、異常内容・対応内容・写真添付が必須です。")
        else:
            save_inspection(vehicle, inspection_date, inspector, meter, statuses, abnormal_detail, action_detail, photos)
            st.success("点検記録を保存しました。")
            st.balloons()

elif menu == "管理者メニュー":
    st.markdown("## 管理者メニュー")
    if require_admin():
        unchecked = today_unchecked()
        abnormal = get_inspections("result = ?", ("使用不可",))
        if abnormal.empty:
            unconfirmed_count = 0
        else:
            unconfirmed_count = len(abnormal[abnormal["manager_confirmed"] == 0])

        inspectors_count = len(get_inspectors(active_only=True))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("本日未点検", len(unchecked))
        c2.metric("異常件数", len(abnormal))
        c3.metric("未承認異常", unconfirmed_count)
        c4.metric("有効点検者", inspectors_count)

        render_system_status()

        if st.button("車両マスター自動修復を実行", use_container_width=True):
            repair_vehicle_master_data()
            st.success("車両マスターと履歴データを自動修復しました。")
            st.rerun()

        st.markdown("### 本日未点検一覧")
        if unchecked.empty:
            st.success("本日の未点検車両はありません。")
        else:
            for _, r in unchecked.iterrows():
                st.error(f"{display_text(r['vehicle_no'])} / {display_text(r['vehicle_name'])} / {VEHICLE_TYPES.get(r['vehicle_type'], r['vehicle_type'])}")

        st.markdown("### 使用禁止中の車両")
        vehicles_locked = get_vehicles(active_only=True)
        vehicles_locked = vehicles_locked[vehicles_locked["use_locked"] == 1] if not vehicles_locked.empty else pd.DataFrame()
        if vehicles_locked.empty:
            st.success("使用禁止中の車両はありません。")
        else:
            for _, r in vehicles_locked.iterrows():
                st.error(f"{display_text(r['vehicle_no'])} / {display_text(r['vehicle_name'])}")

        st.markdown("### 未承認異常")
        if unconfirmed_count == 0:
            st.success("未承認異常はありません。")
        else:
            st.warning(f"未承認異常が{unconfirmed_count}件あります。異常一覧から確認してください。")

        st.markdown("### 管理者QR")
        png = make_qr_png(admin_url())
        st.image(png, caption=admin_url(), width=260)
        st.download_button("管理者QRダウンロード", data=png, file_name="管理者QR.png", mime="image/png")


elif menu == "エラー検知":
    st.markdown("## エラー検知")
    if require_admin():
        render_system_status()
        st.caption("検知対象：未点検、未承認異常、使用禁止車両、点検者未登録、資格者証未添付、1年超過ログ、DB容量。")


elif menu == "車両削除":
    st.markdown("## 車両削除")
    if require_admin():
        df = get_vehicles(active_only=False)
        if df.empty:
            st.info("登録車両はありません。")
        else:
            target = st.selectbox(
                "削除する車両",
                df["vehicle_no"].tolist(),
                format_func=lambda x: f"{display_text(x)} / {display_text(df.loc[df['vehicle_no'] == x, 'vehicle_name'].iloc[0])}",
            )
            st.warning("削除した車両は車両マスターから消えます。過去の点検履歴は残ります。")
            code = st.text_input("管理者コード", type="password")
            if st.button("この車両を削除", type="primary", use_container_width=True):
                if code != ADMIN_CODE:
                    st.error("管理者コードが違います。")
                else:
                    count = force_delete_vehicle(target)
                    if count > 0:
                        st.success("車両を削除しました。")
                    else:
                        st.warning("削除対象が見つかりませんでした。")
                    st.rerun()

elif menu == "異常一覧":
    st.markdown("## 異常一覧")
    if require_admin():
        df = get_inspections("result = ?", ("使用不可",))
        manager_name = st.text_input("管理者名", placeholder="管理者確認に使用")
        if df.empty:
            st.info("異常記録はありません。")
        else:
            for _, row in df.iterrows():
                with st.container(border=True):
                    st.markdown(f"### {row['vehicle_no']} / {row['vehicle_name']}")
                    d = parse_iso_date(row["inspection_date"])
                    st.write(f"点検日：{ja_date(d)}")
                    st.write(f"点検者：{row['inspector']}")
                    st.error("使用不可")
                    st.write(f"異常内容：{row['abnormal_detail']}")
                    st.write(f"対応内容：{row['action_detail']}")
                    render_photos(row)
                    items = get_items(row["id"]).rename(columns={"item_name": "点検項目", "status": "判定"})
                    st.table(items)

                    if row["manager_confirmed"]:
                        st.success(f"管理者確認済：{row['manager_name']} / {row['manager_confirmed_at']}")
                    else:
                        if st.button("管理者確認して使用禁止解除", key=f"confirm_{row['id']}"):
                            if not manager_name:
                                st.warning("管理者名を入力してください。")
                            else:
                                confirm_inspection(row["id"], row["vehicle_no"], manager_name)
                                st.success("管理者確認しました。")
                                st.rerun()

elif menu == "履歴・出力":
    st.markdown("## 履歴・出力")
    if require_admin():
        col1, col2, col3 = st.columns(3)
        start = col1.date_input("開始日", value=date.today().replace(day=1))
        end = col2.date_input("終了日", value=date.today())
        result_filter = col3.selectbox("判定", ["すべて", "使用可", "使用不可"])
        st.caption(f"開始日：{start.strftime('%Y/%m/%d')}")
        st.caption(f"終了日：{end.strftime('%Y/%m/%d')}")

        where = "inspection_date BETWEEN ? AND ?"
        params = [str(start), str(end)]
        if result_filter != "すべて":
            where += " AND result = ?"
            params.append(result_filter)

        df = get_inspections(where, tuple(params))
        st.metric("件数", len(df))

        if df.empty:
            st.info("該当する記録がありません。")
        else:
            for _, row in df.iterrows():
                with st.container(border=True):
                    d = parse_iso_date(row["inspection_date"])
                    c1, c2, c3, c4 = st.columns(4)
                    c1.write(f"**点検日**\\n{ja_date(d)}")
                    c2.write(f"**車両**\\n{row['vehicle_no']} / {row['vehicle_name']}")
                    c3.write(f"**点検者**\\n{row['inspector']}")

                    if row["result"] == "使用不可":
                        c4.error("使用不可")
                    else:
                        c4.success("使用可")

                    if row["meter"]:
                        st.write(f"メーター：{row['meter']}")
                    if row["abnormal_detail"]:
                        st.write(f"異常内容：{row['abnormal_detail']}")
                    if row["action_detail"]:
                        st.write(f"対応内容：{row['action_detail']}")

                    render_photos(row, width=150)

                    new_d = st.date_input("点検日修正", value=d or date.today(), key=f"editdate_{row['id']}")
                    if st.button("この点検日を修正", key=f"updatedate_{row['id']}"):
                        update_inspection_date(row["id"], new_d)
                        st.success("点検日を修正しました。")
                        st.rerun()

            export_df = make_export_df(df)
            st.download_button(
                "Excel出力（表形式）",
                data=excel_bytes(export_df),
                file_name="野田組_車両点検記録.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            st.download_button(
                "CSV出力",
                data=csv_bytes(export_df),
                file_name="野田組_車両点検記録.csv",
                mime="text/csv",
                use_container_width=True
            )

elif menu == "ログ整理":
    st.markdown("## ログ整理")
    if require_admin():
        st.warning("削除したログは元に戻せません。先にExcelまたはCSVで出力してください。")

        st.markdown("### 期間指定で出力・削除")
        c1, c2 = st.columns(2)
        del_start = c1.date_input("削除開始日", value=date.today() - timedelta(days=365))
        del_end = c2.date_input("削除終了日", value=date.today() - timedelta(days=366))

        df_del = get_inspections("inspection_date BETWEEN ? AND ?", (del_start.isoformat(), del_end.isoformat()))
        st.metric("対象件数", len(df_del))

        if not df_del.empty:
            export_df = make_export_df(df_del)
            st.download_button(
                "削除前Excel出力（表形式）",
                data=excel_bytes(export_df),
                file_name="削除前_野田組_車両点検記録.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            st.download_button(
                "削除前CSV出力",
                data=csv_bytes(export_df),
                file_name="削除前_野田組_車両点検記録.csv",
                mime="text/csv",
                use_container_width=True
            )

            confirm_code = st.text_input("削除確認 管理者コード", type="password")
            if st.button("この期間のログを削除", type="primary", use_container_width=True):
                if confirm_code != ADMIN_CODE:
                    st.error("管理者コードが違います。")
                else:
                    count = delete_logs(del_start, del_end)
                    st.success(f"{count}件のログを削除しました。")
                    st.rerun()
        else:
            st.info("指定期間に削除対象ログはありません。")

        st.markdown("### 1年超過ログの削除")
        cutoff = date.today() - timedelta(days=DEFAULT_RETENTION_DAYS)
        old_df = get_inspections("inspection_date < ?", (cutoff.isoformat(),))
        st.write(f"基準日：{cutoff.strftime('%Y/%m/%d')} より前")
        st.metric("1年超過ログ件数", len(old_df))
        code2 = st.text_input("1年超過削除 管理者コード", type="password", key="old_delete_code")
        if st.button("1年超過ログを削除", use_container_width=True):
            if code2 != ADMIN_CODE:
                st.error("管理者コードが違います。")
            else:
                count = delete_logs_older_than(cutoff)
                st.success(f"{count}件の1年超過ログを削除しました。")
                st.rerun()

elif menu == "車両マスター":
    st.markdown("## 車両マスター")
    if require_admin():
        with st.form("vehicle_form"):
            st.markdown("### 車両追加")
            no = st.text_input("車両番号", placeholder="例：FL-003")
            name = st.text_input("車両名", placeholder="例：フォークリフト3号")
            typ = st.selectbox("区分", EDIT_TYPE_KEYS, format_func=lambda x: VEHICLE_TYPES[x])
            next_d = st.date_input("次回点検日", value=date.today() + timedelta(days=30))
            note = st.text_area("備考")
            submitted = st.form_submit_button("登録", use_container_width=True)

            if submitted:
                if not no or not name:
                    st.warning("車両番号と車両名を入力してください。")
                else:
                    ok, msg = add_vehicle(no, name, typ, next_d, note)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

        df = get_vehicles(False)
        st.markdown("### 登録車両")
        if df.empty:
            st.info("登録車両はありません。")
        else:
            for _, r in df.iterrows():
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.write(f"**車両番号**\n{display_text(r['vehicle_no'])}")
                    c2.write(f"**車両名**\n{display_text(r['vehicle_name'])}")
                    c3.write(f"**区分**\n{VEHICLE_TYPES.get(normalize_vehicle_type(r['vehicle_type']), normalize_vehicle_type(r['vehicle_type']))}")
                    c4.write(f"**状態**\n{'有効' if r['active'] else '無効'}")
                    d = parse_iso_date(r.get("next_inspection_date", ""))
                    if d:
                        st.caption(f"次回点検日：{ja_date(d)}")
                    if r.get("use_locked", 0):
                        st.error("使用禁止中")
                    if clean_text(r.get("note")):
                        st.write(f"備考：{clean_text(r['note'])}")

            st.markdown("### 車両の強制削除")
            st.warning("削除できない車両・文字化けした車両はここから削除できます。過去の点検履歴は残ります。")
            delete_target = st.selectbox(
                "削除する車両",
                df["vehicle_no"].tolist(),
                format_func=lambda x: f"{display_text(x)} / {display_text(df.loc[df['vehicle_no'] == x, 'vehicle_name'].iloc[0])}",
                key="force_delete_vehicle_select_master",
            )
            delete_code = st.text_input("車両削除 管理者コード", type="password", key="force_delete_vehicle_code_master")
            if st.button("選択した車両を削除", type="primary", use_container_width=True, key="force_delete_vehicle_button_master"):
                if delete_code != ADMIN_CODE:
                    st.error("管理者コードが違います。")
                else:
                    count = force_delete_vehicle(delete_target)
                    if count > 0:
                        st.success("車両を削除しました。")
                    else:
                        st.warning("削除対象が見つかりませんでした。")
                    st.rerun()

            st.markdown("### 車両情報の編集")
            target = st.selectbox("編集する車両", df["vehicle_no"].tolist())
            row = df[df["vehicle_no"] == target].iloc[0]
            new_name = st.text_input("車両名", value=row["vehicle_name"])
            current_type = normalize_vehicle_type(row.get("vehicle_type", "other"))
            if current_type not in EDIT_TYPE_KEYS:
                current_type = "other"
            new_type = st.selectbox(
                "区分",
                EDIT_TYPE_KEYS,
                index=safe_type_index(current_type, EDIT_TYPE_KEYS) if current_type in EDIT_TYPE_KEYS else 0,
                format_func=lambda x: VEHICLE_TYPES[x]
            )
            old_next = parse_iso_date(row.get("next_inspection_date", ""))
            new_next = st.date_input("次回点検日", value=old_next or date.today())
            new_note = st.text_area("備考", value=row.get("note", "") or "")
            new_active = st.radio("状態", ["有効", "無効"], index=0 if row["active"] else 1, horizontal=True)

            c1, c2, c3 = st.columns(3)
            if c1.button("車両情報を更新", use_container_width=True):
                update_vehicle(target, new_name, new_type, new_active == "有効", new_next, new_note)
                st.success("更新しました。")
                st.rerun()
            if c2.button("使用禁止を手動解除", use_container_width=True):
                reset_vehicle_lock(target)
                st.success("使用禁止を解除しました。")
                st.rerun()
            if c3.button("この車両を削除", use_container_width=True):
                delete_vehicle(target)
                st.success("削除しました。")
                st.rerun()


elif menu == "点検者マスター":
    st.markdown("## 点検者マスター")
    if require_admin():
        st.info("点検者名と資格者証を管理できます。資格者証は最大4枚まで添付できます。")

        with st.form("inspector_add_form"):
            st.markdown("### 点検者追加")
            inspector_name = st.text_input("点検者名", placeholder="例：落合雄平")
            note = st.text_area("備考", placeholder="資格名、教育受講日、有効期限など")
            certs = st.file_uploader(
                "資格者証添付 最大4枚",
                type=["jpg", "jpeg", "png", "webp", "heic"],
                accept_multiple_files=True,
                help="フォークリフト技能講習修了証、車両系建設機械、玉掛け等の画像を添付できます。",
            )
            submitted = st.form_submit_button("点検者を登録", use_container_width=True)
            if submitted:
                if not inspector_name:
                    st.warning("点検者名を入力してください。")
                else:
                    if certs and len(certs) > 4:
                        st.warning("資格者証は最大4枚までです。先頭4枚だけ保存します。")
                        certs = certs[:4]
                    ok, msg = add_inspector(inspector_name, note, certs)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

        inspectors_df = get_inspectors(active_only=False)
        st.markdown("### 登録点検者")
        if inspectors_df.empty:
            st.info("点検者はまだ登録されていません。")
        else:
            for _, r in inspectors_df.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**点検者名**\n{r['inspector_name']}")
                    c2.write(f"**状態**\n{'有効' if r['active'] else '無効'}")
                    c3.write(f"**登録日**\n{r['created_at']}")
                    if clean_text(r.get("note")):
                        st.write(f"備考：{clean_text(r['note'])}")
                    st.write("資格者証")
                    render_certs(r)

            st.markdown("### 点検者情報の編集")
            target_id = st.selectbox(
                "編集する点検者",
                inspectors_df["id"].tolist(),
                format_func=lambda x: inspectors_df.loc[inspectors_df["id"] == x, "inspector_name"].iloc[0],
            )
            row = inspectors_df[inspectors_df["id"] == target_id].iloc[0]
            new_name = st.text_input("点検者名", value=row["inspector_name"])
            new_active = st.radio("状態", ["有効", "無効"], index=0 if row["active"] else 1, horizontal=True)
            new_note = st.text_area("備考", value=row.get("note", "") or "")
            replace_certs = st.checkbox("資格者証を差し替える")
            new_certs = []
            if replace_certs:
                new_certs = st.file_uploader(
                    "新しい資格者証 最大4枚",
                    type=["jpg", "jpeg", "png", "webp", "heic"],
                    accept_multiple_files=True,
                    key="replace_certs",
                )
                if new_certs and len(new_certs) > 4:
                    st.warning("資格者証は最大4枚までです。先頭4枚だけ保存します。")
                    new_certs = new_certs[:4]

            c1, c2 = st.columns(2)
            if c1.button("点検者情報を更新", use_container_width=True):
                if not new_name:
                    st.warning("点検者名を入力してください。")
                else:
                    update_inspector(target_id, new_name, new_active == "有効", new_note, new_certs, replace_certs)
                    st.success("更新しました。")
                    st.rerun()

            if c2.button("この点検者を削除", use_container_width=True):
                delete_inspector(target_id)
                st.success("削除しました。")
                st.rerun()


elif menu == "QRコード発行":
    st.markdown("## QRコード発行")
    if require_admin():
        vehicles = get_vehicles(True)
        if vehicles.empty:
            st.warning("車両マスターに車両を登録してください。")
        else:
            selected_no = st.selectbox(
                "QRを作る車両",
                vehicles["vehicle_no"].tolist(),
                format_func=lambda no: f"{display_text(no)} / {display_text(vehicles.loc[vehicles['vehicle_no'] == no, 'vehicle_name'].iloc[0])}"
            )
            url = qr_url(selected_no)
            png = make_qr_png(url)
            st.code(url)
            st.image(png, caption=url, width=280)
            st.download_button("車両QRダウンロード", data=png, file_name=f"{selected_no}_QR.png", mime="image/png", use_container_width=True)

            st.markdown("### 管理者用QR")
            admin_png = make_qr_png(admin_url())
            st.code(admin_url())
            st.image(admin_png, caption=admin_url(), width=280)
            st.download_button("管理者QRダウンロード", data=admin_png, file_name="管理者QR.png", mime="image/png", use_container_width=True)

elif menu == "QR印刷台紙":
    st.markdown("## QR印刷台紙")
    if require_admin():
        st.info("全車両のQRと管理者QRを一覧表示します。ブラウザの印刷機能でPDF保存・印刷できます。")
        st.caption(f"発行日：{ja_date(date.today())}")
        vehicles = get_vehicles(True)
        cols = st.columns(3)
        for i, (_, row) in enumerate(vehicles.iterrows()):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"### {row['vehicle_no']}")
                    st.write(row["vehicle_name"])
                    st.caption(VEHICLE_TYPES.get(row["vehicle_type"], row["vehicle_type"]))
                    url = qr_url(row["vehicle_no"])
                    st.image(make_qr_png(url), width=220)
                    st.caption(url)
        st.divider()
        st.markdown("### 管理者用QR")
        st.image(make_qr_png(admin_url()), width=260)
        st.caption(admin_url())
