
import os
import sqlite3
import urllib.parse
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
import qrcode
import streamlit as st

st.set_page_config(
    page_title="野田組 フォークリフト始業前点検",
    page_icon="🚜",
    layout="wide",
)

APP_URL = "https://heavy-vehicle-check-ghka28mxhavp4qrjpnkb7b.streamlit.app"
ADMIN_CODE = "1224"
DB_PATH = "forklift_check.db"
RETENTION_DAYS = 1095
WEEK_JA = ["月", "火", "水", "木", "金", "土", "日"]

CHECK_ITEMS = {
    "走行装置": [
        "ブレーキ",
        "駐車ブレーキ",
        "ハンドル・操舵装置",
        "タイヤ・ホイール",
    ],
    "荷役装置": [
        "フォーク損傷",
        "フォーク固定ピン",
        "バックレスト",
        "マスト損傷",
        "リフトチェーン張り",
        "リフトチェーン給油状態",
        "荷重計（装備車のみ）",
    ],
    "油圧装置": [
        "リフトシリンダー損傷",
        "チルトシリンダー損傷",
        "油圧ホース",
        "油漏れ",
    ],
    "安全装置": [
        "ヘッドガード",
        "シートベルト",
        "ライト",
        "バックブザー",
        "ホーン",
        "ミラー",
    ],
    "エンジン・電源": [
        "バッテリー",
        "燃料",
        "エンジンオイル",
        "冷却水",
    ],
    "外観": [
        "車体損傷",
        "ボルト・ナット緩み",
        "異物付着",
    ],
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


def ja_date(d):
    if not d:
        return ""
    return f"{d.year}年{d.month}月{d.day}日（{WEEK_JA[d.weekday()]}）"


def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    con = connect()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS forklifts (
            forklift_no TEXT PRIMARY KEY,
            forklift_name TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            use_locked INTEGER DEFAULT 0,
            next_inspection_date TEXT,
            note TEXT,
            created_at TEXT NOT NULL
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspected_at TEXT NOT NULL,
            inspection_date TEXT NOT NULL,
            forklift_no TEXT NOT NULL,
            forklift_name TEXT NOT NULL,
            inspector TEXT NOT NULL,
            meter TEXT,
            result TEXT NOT NULL,
            abnormal_detail TEXT,
            action_detail TEXT,
            photo1_name TEXT,
            photo1_bytes BLOB,
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspection_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            item_name TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    con.commit()
    con.close()


def seed_data():
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM forklifts")
    if cur.fetchone()[0] == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        next_date = (date.today() + timedelta(days=30)).isoformat()
        for no, name in [("FL-001", "フォークリフト1号"), ("FL-002", "フォークリフト2号")]:
            cur.execute(
                """
                INSERT INTO forklifts(
                    forklift_no, forklift_name, active, use_locked, next_inspection_date, note, created_at
                ) VALUES (?, ?, 1, 0, ?, '', ?)
                """,
                (no, name, next_date, now),
            )
    con.commit()
    con.close()


def get_forklifts(active_only=True):
    con = connect()
    sql = "SELECT * FROM forklifts"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY forklift_no"
    df = pd.read_sql_query(sql, con)
    con.close()
    if not df.empty:
        for col in ["forklift_no", "forklift_name", "note"]:
            if col in df.columns:
                df[col] = df[col].apply(clean_text)
    return df


def get_forklift(forklift_no):
    con = connect()
    df = pd.read_sql_query(
        "SELECT * FROM forklifts WHERE forklift_no = ?",
        con,
        params=(clean_text(forklift_no),),
    )
    con.close()
    if df.empty:
        return None
    for col in ["forklift_no", "forklift_name", "note"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_text)
    return df.iloc[0].to_dict()


def add_forklift(no, name, next_date, note):
    con = connect()
    try:
        con.execute(
            """
            INSERT INTO forklifts(
                forklift_no, forklift_name, active, use_locked, next_inspection_date, note, created_at
            ) VALUES (?, ?, 1, 0, ?, ?, ?)
            """,
            (
                clean_text(no),
                clean_text(name),
                next_date.isoformat(),
                clean_text(note),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        con.commit()
        return True, "フォークリフトを登録しました。"
    except sqlite3.IntegrityError:
        return False, "同じ車両番号が既にあります。"
    finally:
        con.close()


def update_forklift(no, name, active, next_date, note):
    con = connect()
    con.execute(
        """
        UPDATE forklifts
        SET forklift_name = ?, active = ?, next_inspection_date = ?, note = ?
        WHERE forklift_no = ?
        """,
        (
            clean_text(name),
            1 if active else 0,
            next_date.isoformat(),
            clean_text(note),
            clean_text(no),
        ),
    )
    con.commit()
    con.close()


def delete_forklift(no):
    con = connect()
    cur = con.cursor()
    cur.execute("DELETE FROM forklifts WHERE forklift_no = ?", (clean_text(no),))
    deleted = cur.rowcount
    con.commit()
    con.close()
    return deleted


def reset_forklift_lock(no):
    con = connect()
    con.execute("UPDATE forklifts SET use_locked = 0 WHERE forklift_no = ?", (clean_text(no),))
    con.commit()
    con.close()


def get_inspectors(active_only=True):
    con = connect()
    sql = "SELECT * FROM inspectors"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY inspector_name"
    df = pd.read_sql_query(sql, con)
    con.close()
    if not df.empty:
        df["inspector_name"] = df["inspector_name"].apply(clean_text)
        if "note" in df.columns:
            df["note"] = df["note"].apply(clean_text)
    return df


def add_inspector(name, note, certs):
    cert_data = []
    for cert in (certs or [])[:4]:
        cert_data.append((cert.name, cert.getvalue()))
    while len(cert_data) < 4:
        cert_data.append(("", None))

    con = connect()
    try:
        con.execute(
            """
            INSERT INTO inspectors(
                inspector_name, active, note,
                cert1_name, cert1_bytes, cert2_name, cert2_bytes,
                cert3_name, cert3_bytes, cert4_name, cert4_bytes,
                created_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_text(name),
                clean_text(note),
                cert_data[0][0], cert_data[0][1],
                cert_data[1][0], cert_data[1][1],
                cert_data[2][0], cert_data[2][1],
                cert_data[3][0], cert_data[3][1],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        con.commit()
        return True, "点検者を登録しました。"
    except sqlite3.IntegrityError:
        return False, "同じ点検者名が既にあります。"
    finally:
        con.close()


def update_inspector(inspector_id, name, active, note, certs, replace_certs):
    con = connect()
    if replace_certs:
        cert_data = []
        for cert in (certs or [])[:4]:
            cert_data.append((cert.name, cert.getvalue()))
        while len(cert_data) < 4:
            cert_data.append(("", None))
        con.execute(
            """
            UPDATE inspectors
            SET inspector_name = ?, active = ?, note = ?,
                cert1_name = ?, cert1_bytes = ?,
                cert2_name = ?, cert2_bytes = ?,
                cert3_name = ?, cert3_bytes = ?,
                cert4_name = ?, cert4_bytes = ?
            WHERE id = ?
            """,
            (
                clean_text(name), 1 if active else 0, clean_text(note),
                cert_data[0][0], cert_data[0][1],
                cert_data[1][0], cert_data[1][1],
                cert_data[2][0], cert_data[2][1],
                cert_data[3][0], cert_data[3][1],
                inspector_id,
            ),
        )
    else:
        con.execute(
            "UPDATE inspectors SET inspector_name = ?, active = ?, note = ? WHERE id = ?",
            (clean_text(name), 1 if active else 0, clean_text(note), inspector_id),
        )
    con.commit()
    con.close()


def delete_inspector(inspector_id):
    con = connect()
    con.execute("DELETE FROM inspectors WHERE id = ?", (inspector_id,))
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


def get_items(inspection_id):
    con = connect()
    df = pd.read_sql_query(
        "SELECT category, item_name, status FROM inspection_items WHERE inspection_id = ?",
        con,
        params=(inspection_id,),
    )
    con.close()
    return df


def get_today_inspection(forklift_no):
    df = get_inspections(
        "forklift_no = ? AND inspection_date = ?",
        (clean_text(forklift_no), date.today().isoformat()),
    )
    if df.empty:
        return None
    return df.iloc[0]


def save_inspection(forklift, inspection_date, inspector, meter, statuses, abnormal_detail, action_detail, photos):
    has_abnormal = any(status == "異常あり" for status in statuses.values())
    result = "使用不可" if has_abnormal else "使用可"

    photo_data = []
    for photo in (photos or [])[:4]:
        photo_data.append((photo.name, photo.getvalue()))
    while len(photo_data) < 4:
        photo_data.append(("", None))

    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO inspections(
            inspected_at, inspection_date, forklift_no, forklift_name,
            inspector, meter, result, abnormal_detail, action_detail,
            photo1_name, photo1_bytes, photo2_name, photo2_bytes,
            photo3_name, photo3_bytes, photo4_name, photo4_bytes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            inspection_date.isoformat(),
            forklift["forklift_no"],
            forklift["forklift_name"],
            clean_text(inspector),
            clean_text(meter),
            result,
            clean_text(abnormal_detail),
            clean_text(action_detail),
            photo_data[0][0], photo_data[0][1],
            photo_data[1][0], photo_data[1][1],
            photo_data[2][0], photo_data[2][1],
            photo_data[3][0], photo_data[3][1],
        ),
    )
    inspection_id = cur.lastrowid

    for category, items in CHECK_ITEMS.items():
        for item in items:
            cur.execute(
                "INSERT INTO inspection_items(inspection_id, category, item_name, status) VALUES (?, ?, ?, ?)",
                (inspection_id, category, item, statuses.get(item, "対象外")),
            )

    if has_abnormal:
        cur.execute("UPDATE forklifts SET use_locked = 1 WHERE forklift_no = ?", (forklift["forklift_no"],))

    con.commit()
    con.close()


def confirm_inspection(inspection_id, forklift_no, manager_name):
    con = connect()
    con.execute(
        """
        UPDATE inspections
        SET manager_confirmed = 1, manager_name = ?, manager_confirmed_at = ?
        WHERE id = ?
        """,
        (clean_text(manager_name), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inspection_id),
    )
    con.execute("UPDATE forklifts SET use_locked = 0 WHERE forklift_no = ?", (clean_text(forklift_no),))
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
    cur.execute(
        "SELECT id FROM inspections WHERE inspection_date BETWEEN ? AND ?",
        (start_date.isoformat(), end_date.isoformat()),
    )
    ids = [row[0] for row in cur.fetchall()]
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        cur.execute(f"DELETE FROM inspection_items WHERE inspection_id IN ({placeholders})", ids)
        cur.execute(f"DELETE FROM inspections WHERE id IN ({placeholders})", ids)
    con.commit()
    con.close()
    return len(ids)


def make_qr_png(url):
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def qr_url(forklift_no):
    return APP_URL.rstrip("/") + "/?forklift=" + urllib.parse.quote(str(forklift_no), safe="")


def admin_url():
    return APP_URL.rstrip("/") + "/?admin=true"


def get_query_value(key):
    try:
        value = st.query_params.get(key, "")
    except Exception:
        return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return urllib.parse.unquote(str(value or ""))


def parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


def render_photos(row, width=160):
    pairs = [
        ("photo1_name", "photo1_bytes"),
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


def today_unchecked():
    forklifts = get_forklifts(True)
    checked = get_inspections("inspection_date = ?", (date.today().isoformat(),))
    checked_set = set(checked["forklift_no"].tolist()) if not checked.empty else set()
    if forklifts.empty:
        return pd.DataFrame()
    return forklifts[~forklifts["forklift_no"].isin(checked_set)]


def system_checks():
    errors = []
    warnings = []

    forklifts = get_forklifts(True)
    inspectors = get_inspectors(True)
    abnormal = get_inspections("result = ?", ("使用不可",))

    if forklifts.empty:
        errors.append("フォークリフトが登録されていません。")

    if inspectors.empty:
        warnings.append("点検者が登録されていません。")

    if not forklifts.empty:
        locked = forklifts[forklifts["use_locked"] == 1]
        if len(locked) > 0:
            errors.append(f"使用禁止中のフォークリフトが{len(locked)}台あります。")

    if not abnormal.empty:
        unconfirmed = abnormal[abnormal["manager_confirmed"] == 0]
        if len(unconfirmed) > 0:
            errors.append(f"未承認の異常記録が{len(unconfirmed)}件あります。")

    unchecked = today_unchecked()
    if len(unchecked) > 0:
        warnings.append(f"本日未点検のフォークリフトが{len(unchecked)}台あります。")

    cutoff = date.today() - timedelta(days=RETENTION_DAYS)
    old_logs = get_inspections("inspection_date < ?", (cutoff.isoformat(),))
    if len(old_logs) > 0:
        warnings.append(f"3年超過ログが{len(old_logs)}件あります。")

    try:
        if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 200 * 1024 * 1024:
            warnings.append("データベース容量が200MBを超えています。ログ整理を推奨します。")
    except Exception:
        pass

    return errors, warnings


def make_export_df(df):
    export_df = df.drop(columns=["photo1_bytes", "photo2_bytes", "photo3_bytes", "photo4_bytes"], errors="ignore").copy()
    export_df = export_df.rename(columns={
        "id": "ID",
        "inspected_at": "保存日時",
        "inspection_date": "点検日",
        "forklift_no": "車両番号",
        "forklift_name": "車両名",
        "inspector": "点検者",
        "meter": "アワーメーター",
        "result": "判定",
        "abnormal_detail": "異常内容",
        "action_detail": "対応内容",
        "photo1_name": "写真1",
        "photo2_name": "写真2",
        "photo3_name": "写真3",
        "photo4_name": "写真4",
        "manager_confirmed": "管理者確認",
        "manager_name": "管理者名",
        "manager_confirmed_at": "管理者確認日時",
    })

    if "管理者確認" in export_df.columns:
        export_df["管理者確認"] = export_df["管理者確認"].apply(lambda x: "確認済" if x else "未確認")

    item_texts = []
    for _, row in df.iterrows():
        items = get_items(row["id"])
        item_texts.append(" / ".join([
            f"{item_row['category']}:{item_row['item_name']}={item_row['status']}"
            for _, item_row in items.iterrows()
        ]))
    export_df["点検項目"] = item_texts
    return export_df


def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")


def excel_bytes(export_df):
    excel_buf = BytesIO()
    with pd.ExcelWriter(excel_buf, engine="xlsxwriter") as writer:
        workbook = writer.book

        title_fmt = workbook.add_format({
            "bold": True, "font_size": 18, "align": "center", "valign": "vcenter",
            "fg_color": "#1F4E78", "font_color": "white"
        })
        header_fmt = workbook.add_format({
            "bold": True, "font_color": "white", "fg_color": "#305496",
            "border": 1, "align": "center"
        })
        cell_fmt = workbook.add_format({"border": 1, "valign": "top", "text_wrap": True})
        ok_fmt = workbook.add_format({"border": 1, "fg_color": "#E2F0D9", "font_color": "#375623"})
        ng_fmt = workbook.add_format({"border": 1, "fg_color": "#FCE4D6", "font_color": "#9C0006"})

        cover = workbook.add_worksheet("表紙")
        cover.merge_range("A1:H2", "野田組 フォークリフト始業前点検記録", title_fmt)
        cover.write("A4", "出力日時")
        cover.write("B4", datetime.now().strftime("%Y/%m/%d %H:%M"))
        cover.write("A5", "出力件数")
        cover.write("B5", len(export_df))
        cover.set_column("A:H", 22)

        sheet_name = "点検履歴"
        export_df.to_excel(writer, index=False, sheet_name=sheet_name, startrow=3)
        ws = writer.sheets[sheet_name]

        if len(export_df.columns) > 0:
            ws.merge_range(0, 0, 1, len(export_df.columns) - 1, "野田組 フォークリフト始業前点検 一覧表", title_fmt)
            for col_idx, col_name in enumerate(export_df.columns):
                ws.write(3, col_idx, col_name, header_fmt)

            for row_idx in range(len(export_df)):
                for col_idx, col_name in enumerate(export_df.columns):
                    value = export_df.iloc[row_idx, col_idx]
                    if col_name == "判定" and str(value) == "使用不可":
                        fmt = ng_fmt
                    elif col_name == "判定" and str(value) == "使用可":
                        fmt = ok_fmt
                    else:
                        fmt = cell_fmt
                    ws.write(row_idx + 4, col_idx, "" if pd.isna(value) else value, fmt)

            ws.freeze_panes(4, 0)
            ws.autofilter(3, 0, len(export_df) + 3, len(export_df.columns) - 1)
            widths = {
                "点検項目": 60,
                "異常内容": 34,
                "対応内容": 34,
                "車両名": 22,
                "保存日時": 18,
                "管理者確認日時": 18,
            }
            for col_idx, col_name in enumerate(export_df.columns):
                ws.set_column(col_idx, col_idx, widths.get(col_name, 16))
            ws.set_landscape()
            ws.fit_to_pages(1, 0)

    return excel_buf.getvalue()


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


def render_quick_forklift_register(prefix="empty"):
    st.markdown("### フォークリフトを登録してください")
    with st.form(f"{prefix}_forklift_register_form"):
        no = st.text_input("車両番号", placeholder="例：FL-001", key=f"{prefix}_forklift_no")
        name = st.text_input("車両名", placeholder="例：フォークリフト1号", key=f"{prefix}_forklift_name")
        next_date = st.date_input("次回点検日", value=date.today() + timedelta(days=30), key=f"{prefix}_next_date")
        note = st.text_area("備考", key=f"{prefix}_note")
        submitted = st.form_submit_button("フォークリフトを登録", use_container_width=True)
        if submitted:
            if not clean_text(no) or not clean_text(name):
                st.warning("車両番号と車両名を入力してください。")
            else:
                ok, msg = add_forklift(no, name, next_date, note)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)


init_db()
seed_data()

st.markdown("""
<style>
.block-container { padding-top: 1rem; max-width: 1120px; }
div.stButton > button { border-radius: 10px; font-weight: 700; }
h1,h2,h3 { line-height: 1.25; }
@media print {
  section[data-testid="stSidebar"], header, footer, .stButton { display:none !important; }
}
</style>
""", unsafe_allow_html=True)

st.title("🚜 野田組 フォークリフト始業前点検")
st.caption("フォークリフト専用 / 労働安全衛生法対応 / QR管理 / 3年保存 / 管理者承認")

query_forklift = get_query_value("forklift")
query_admin = get_query_value("admin") == "true"

forklifts_now = get_forklifts(True)
valid_nos = set(forklifts_now["forklift_no"].tolist()) if not forklifts_now.empty else set()
if query_forklift and query_forklift not in valid_nos:
    st.warning("QRコードの車両番号がマスターにありません。車両を選択してください。")
    query_forklift = ""

if query_forklift:
    st.success(f"QRコードから車両を固定しました：{query_forklift}")

menu_options = [
    "点検入力",
    "管理者メニュー",
    "エラー検知",
    "異常一覧",
    "履歴・出力",
    "ログ整理",
    "フォークリフトマスター",
    "点検者マスター",
    "QRコード発行",
    "QR印刷台紙",
]
default_menu = "管理者メニュー" if query_admin else "点検入力"
menu = st.sidebar.radio("メニュー", menu_options, index=menu_options.index(default_menu))


if menu == "点検入力":
    st.markdown("## 点検入力")
    forklifts = get_forklifts(True)

    if forklifts.empty:
        st.warning("登録フォークリフトはありません。")
        render_quick_forklift_register("inspection_empty")
        st.stop()

    options = forklifts["forklift_no"].tolist()
    if query_forklift and query_forklift in options:
        selected_no = query_forklift
        selected_name = forklifts.loc[forklifts["forklift_no"] == selected_no, "forklift_name"].iloc[0]
        st.info(f"車両固定：{selected_no} / {selected_name}")
    else:
        selected_no = st.selectbox(
            "車両",
            options,
            format_func=lambda no: f"{no} / {forklifts.loc[forklifts['forklift_no'] == no, 'forklift_name'].iloc[0]}",
        )

    forklift = get_forklift(selected_no)
    if forklift is None:
        st.error("フォークリフト情報が見つかりません。")
        st.stop()

    c1, c2 = st.columns(2)
    c1.metric("車両番号", forklift["forklift_no"])
    c2.metric("車両名", forklift["forklift_name"])

    today_done = get_today_inspection(selected_no)
    if today_done is not None and query_forklift:
        st.success("本日の点検は完了しています。")
        st.write(f"点検者：{today_done['inspector']}")
        st.write(f"保存日時：{today_done['inspected_at']}")
        if today_done["result"] == "使用不可":
            st.error("判定：使用不可")
        else:
            st.success("判定：使用可")

        with st.expander("本日の点検内容を確認"):
            items_df = get_items(today_done["id"]).rename(columns={
                "category": "分類",
                "item_name": "点検項目",
                "status": "判定",
            })
            st.table(items_df)
            render_photos(today_done)

        force_recheck = st.checkbox("再点検として新しく記録する")
        if not force_recheck:
            st.info("再点検する場合だけチェックを入れてください。")
            st.stop()
    elif today_done is not None:
        st.info("この車両は本日すでに点検済みです。必要なら再点検として保存できます。")

    inspection_date = st.date_input("点検日", value=date.today())
    st.caption(f"点検日：{ja_date(inspection_date)}")

    if forklift.get("use_locked", 0):
        st.error("このフォークリフトは異常報告により使用禁止中です。管理者確認まで使用しないでください。")

    inspectors_df = get_inspectors(True)
    if inspectors_df.empty:
        inspector = st.text_input("点検者名", placeholder="氏名")
        st.caption("点検者マスター未登録のため手入力です。")
    else:
        inspector = st.selectbox("点検者", inspectors_df["inspector_name"].tolist())

    meter = st.text_input("アワーメーター", placeholder="例：1234h")

    st.markdown("### 点検項目")
    st.caption("判定：良好 / 要整備（使用可） / 異常あり / 対象外。異常ありは使用停止・写真添付必須です。")

    statuses = {}
    for category, items in CHECK_ITEMS.items():
        st.markdown(f"#### {category}")
        for item in items:
            with st.container(border=True):
                st.markdown(f"**{item}**")
                statuses[item] = st.radio(
                    "判定",
                    ["良好", "要整備（使用可）", "異常あり", "対象外"],
                    horizontal=True,
                    key=f"{selected_no}_{category}_{item}",
                )

    has_abnormal = any(value == "異常あり" for value in statuses.values())
    abnormal_detail = ""
    action_detail = ""
    photos = []

    if has_abnormal:
        st.error("異常あり：このフォークリフトは使用不可として保存されます。")
        abnormal_detail = st.text_area("異常内容 ※必須", placeholder="どこが、どう悪いか")
        action_detail = st.text_area("対応内容 ※必須", placeholder="使用停止、修理依頼、管理者報告など")
        photos = st.file_uploader(
            "写真添付 ※必須・最大4枚",
            type=["jpg", "jpeg", "png", "webp", "heic"],
            accept_multiple_files=True,
        )
        if photos and len(photos) > 4:
            st.warning("写真は最大4枚までです。先頭4枚だけ保存します。")
            photos = photos[:4]

    if has_abnormal:
        st.error("最終判定：使用不可")
    else:
        st.success("最終判定：使用可")

    if st.button("点検記録を保存", type="primary", use_container_width=True):
        if not clean_text(inspector):
            st.warning("点検者名を入力してください。")
        elif has_abnormal and (not clean_text(abnormal_detail) or not clean_text(action_detail) or not photos):
            st.warning("異常ありの場合は、異常内容・対応内容・写真添付が必須です。")
        else:
            save_inspection(forklift, inspection_date, inspector, meter, statuses, abnormal_detail, action_detail, photos)
            st.success("点検記録を保存しました。")
            st.balloons()


elif menu == "管理者メニュー":
    st.markdown("## 管理者メニュー")
    if require_admin():
        errors, warnings = system_checks()
        unchecked = today_unchecked()
        abnormal = get_inspections("result = ?", ("使用不可",))
        unconfirmed = abnormal[abnormal["manager_confirmed"] == 0] if not abnormal.empty else pd.DataFrame()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("本日未点検", len(unchecked))
        c2.metric("異常件数", len(abnormal))
        c3.metric("未承認異常", len(unconfirmed))
        c4.metric("登録車両", len(get_forklifts(False)))

        st.markdown("### システム状態")
        if not errors and not warnings:
            st.success("現在、重大な未対応・設定不備は検知されていません。")
        for error in errors:
            st.error(error)
        for warning in warnings:
            st.warning(warning)

        st.markdown("### 本日未点検一覧")
        if unchecked.empty:
            st.success("本日の未点検フォークリフトはありません。")
        else:
            for _, row in unchecked.iterrows():
                st.error(f"{row['forklift_no']} / {row['forklift_name']}")

        if get_forklifts(True).empty:
            render_quick_forklift_register("admin_empty")

        st.markdown("### 管理者QR")
        png = make_qr_png(admin_url())
        st.image(png, caption=admin_url(), width=260)
        st.download_button("管理者QRダウンロード", data=png, file_name="管理者QR.png", mime="image/png")


elif menu == "エラー検知":
    st.markdown("## エラー検知")
    if require_admin():
        errors, warnings = system_checks()
        if not errors and not warnings:
            st.success("エラーは検知されていません。")
        for error in errors:
            st.error(error)
        for warning in warnings:
            st.warning(warning)


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
                    st.markdown(f"### {row['forklift_no']} / {row['forklift_name']}")
                    d = parse_iso_date(row["inspection_date"])
                    st.write(f"点検日：{ja_date(d)}")
                    st.write(f"点検者：{row['inspector']}")
                    st.error("使用不可")
                    st.write(f"異常内容：{clean_text(row['abnormal_detail'])}")
                    st.write(f"対応内容：{clean_text(row['action_detail'])}")
                    render_photos(row)

                    items = get_items(row["id"]).rename(columns={
                        "category": "分類",
                        "item_name": "点検項目",
                        "status": "判定",
                    })
                    st.table(items)

                    if row["manager_confirmed"]:
                        st.success(f"管理者確認済：{row['manager_name']} / {row['manager_confirmed_at']}")
                    else:
                        if st.button("管理者確認して使用禁止解除", key=f"confirm_{row['id']}"):
                            if not clean_text(manager_name):
                                st.warning("管理者名を入力してください。")
                            else:
                                confirm_inspection(row["id"], row["forklift_no"], manager_name)
                                st.success("管理者確認しました。")
                                st.rerun()


elif menu == "履歴・出力":
    st.markdown("## 履歴・出力")
    if require_admin():
        col1, col2, col3 = st.columns(3)
        start_date = col1.date_input("開始日", value=date.today().replace(day=1))
        end_date = col2.date_input("終了日", value=date.today())
        result_filter = col3.selectbox("判定", ["すべて", "使用可", "使用不可"])

        where = "inspection_date BETWEEN ? AND ?"
        params = [start_date.isoformat(), end_date.isoformat()]
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
                    c1.write(f"**点検日**\n{ja_date(d)}")
                    c2.write(f"**車両**\n{row['forklift_no']} / {row['forklift_name']}")
                    c3.write(f"**点検者**\n{row['inspector']}")
                    if row["result"] == "使用不可":
                        c4.error("使用不可")
                    else:
                        c4.success("使用可")

                    render_photos(row, width=150)

                    new_date = st.date_input("点検日修正", value=d or date.today(), key=f"editdate_{row['id']}")
                    if st.button("この点検日を修正", key=f"updatedate_{row['id']}"):
                        update_inspection_date(row["id"], new_date)
                        st.success("点検日を修正しました。")
                        st.rerun()

            export_df = make_export_df(df)
            st.download_button(
                "Excel出力（表形式）",
                data=excel_bytes(export_df),
                file_name="野田組_フォークリフト始業前点検.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.download_button(
                "CSV出力",
                data=csv_bytes(export_df),
                file_name="野田組_フォークリフト始業前点検.csv",
                mime="text/csv",
                use_container_width=True,
            )


elif menu == "ログ整理":
    st.markdown("## ログ整理")
    if require_admin():
        st.warning("削除したログは元に戻せません。先にExcelまたはCSVで出力してください。")
        c1, c2 = st.columns(2)
        delete_start = c1.date_input("削除開始日", value=date.today() - timedelta(days=RETENTION_DAYS))
        delete_end = c2.date_input("削除終了日", value=date.today() - timedelta(days=RETENTION_DAYS + 1))
        target_df = get_inspections("inspection_date BETWEEN ? AND ?", (delete_start.isoformat(), delete_end.isoformat()))
        st.metric("対象件数", len(target_df))

        if not target_df.empty:
            export_df = make_export_df(target_df)
            st.download_button(
                "削除前Excel出力",
                data=excel_bytes(export_df),
                file_name="削除前_フォークリフト点検.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            code = st.text_input("削除確認 管理者コード", type="password")
            if st.button("この期間のログを削除", type="primary", use_container_width=True):
                if code != ADMIN_CODE:
                    st.error("管理者コードが違います。")
                else:
                    count = delete_logs(delete_start, delete_end)
                    st.success(f"{count}件のログを削除しました。")
                    st.rerun()


elif menu == "フォークリフトマスター":
    st.markdown("## フォークリフトマスター")
    if require_admin():
        with st.form("forklift_add_form"):
            st.markdown("### フォークリフト追加")
            no = st.text_input("車両番号", placeholder="例：FL-003")
            name = st.text_input("車両名", placeholder="例：フォークリフト3号")
            next_date = st.date_input("次回点検日", value=date.today() + timedelta(days=30))
            note = st.text_area("備考")
            submitted = st.form_submit_button("登録", use_container_width=True)
            if submitted:
                if not clean_text(no) or not clean_text(name):
                    st.warning("車両番号と車両名を入力してください。")
                else:
                    ok, msg = add_forklift(no, name, next_date, note)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        df = get_forklifts(False)
        st.markdown("### 登録フォークリフト")

        if df.empty:
            st.info("登録フォークリフトはありません。")
            render_quick_forklift_register("master_empty")
        else:
            with st.expander("フォークリフトを選んで削除する", expanded=False):
                target_no = st.selectbox(
                    "削除するフォークリフト",
                    df["forklift_no"].tolist(),
                    format_func=lambda x: f"{x} / {df.loc[df['forklift_no'] == x, 'forklift_name'].iloc[0]}",
                    key="delete_forklift_select",
                )
                code = st.text_input("削除用 管理者コード", type="password", key="delete_forklift_code")
                if st.button("選択したフォークリフトを削除", type="primary", use_container_width=True):
                    if code != ADMIN_CODE:
                        st.error("管理者コードが違います。")
                    else:
                        deleted = delete_forklift(target_no)
                        if deleted > 0:
                            st.success("削除しました。")
                        else:
                            st.warning("削除対象が見つかりませんでした。")
                        st.rerun()

            for _, row in df.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**車両番号**\n{row['forklift_no']}")
                    c2.write(f"**車両名**\n{row['forklift_name']}")
                    c3.write(f"**状態**\n{'有効' if row['active'] else '無効'}")
                    if clean_text(row.get("note")):
                        st.write(f"備考：{clean_text(row['note'])}")
                    if row.get("use_locked", 0):
                        st.error("使用禁止中")

                    with st.expander("このフォークリフトを削除"):
                        st.warning("このフォークリフトをマスターから削除します。過去の点検履歴は残ります。")
                        code_each = st.text_input("管理者コード", type="password", key=f"delete_code_{row['forklift_no']}")
                        if st.button("削除実行", key=f"delete_btn_{row['forklift_no']}", use_container_width=True):
                            if code_each != ADMIN_CODE:
                                st.error("管理者コードが違います。")
                            else:
                                deleted = delete_forklift(row["forklift_no"])
                                if deleted > 0:
                                    st.success("削除しました。")
                                else:
                                    st.warning("削除対象が見つかりませんでした。")
                                st.rerun()

            st.markdown("### フォークリフト情報の編集")
            edit_target = st.selectbox("編集するフォークリフト", df["forklift_no"].tolist(), key="edit_forklift")
            row = df[df["forklift_no"] == edit_target].iloc[0]
            new_name = st.text_input("車両名", value=row["forklift_name"])
            old_next = parse_iso_date(row.get("next_inspection_date", ""))
            new_next = st.date_input("次回点検日", value=old_next or date.today())
            new_note = st.text_area("備考", value=clean_text(row.get("note", "")))
            new_active = st.radio("状態", ["有効", "無効"], index=0 if row["active"] else 1, horizontal=True)

            c1, c2 = st.columns(2)
            if c1.button("情報を更新", use_container_width=True):
                update_forklift(edit_target, new_name, new_active == "有効", new_next, new_note)
                st.success("更新しました。")
                st.rerun()

            if c2.button("使用禁止を手動解除", use_container_width=True):
                reset_forklift_lock(edit_target)
                st.success("使用禁止を解除しました。")
                st.rerun()


elif menu == "点検者マスター":
    st.markdown("## 点検者マスター")
    if require_admin():
        with st.form("inspector_add_form"):
            st.markdown("### 点検者追加")
            name = st.text_input("点検者名")
            note = st.text_area("備考", placeholder="フォークリフト技能講習修了証など")
            certs = st.file_uploader(
                "資格者証添付 最大4枚",
                type=["jpg", "jpeg", "png", "webp", "heic"],
                accept_multiple_files=True,
            )
            submitted = st.form_submit_button("登録", use_container_width=True)
            if submitted:
                if not clean_text(name):
                    st.warning("点検者名を入力してください。")
                else:
                    if certs and len(certs) > 4:
                        certs = certs[:4]
                    ok, msg = add_inspector(name, note, certs)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        df = get_inspectors(False)
        if df.empty:
            st.info("点検者は未登録です。")
        else:
            for _, row in df.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns(2)
                    c1.write(f"**点検者名**\n{row['inspector_name']}")
                    c2.write(f"**状態**\n{'有効' if row['active'] else '無効'}")
                    if clean_text(row.get("note")):
                        st.write(f"備考：{clean_text(row['note'])}")
                    render_certs(row)

            st.markdown("### 点検者情報の編集")
            target_id = st.selectbox(
                "編集する点検者",
                df["id"].tolist(),
                format_func=lambda x: df.loc[df["id"] == x, "inspector_name"].iloc[0],
            )
            row = df[df["id"] == target_id].iloc[0]
            new_name = st.text_input("点検者名", value=row["inspector_name"])
            new_active = st.radio("状態", ["有効", "無効"], index=0 if row["active"] else 1, horizontal=True, key="inspector_active")
            new_note = st.text_area("備考", value=clean_text(row.get("note", "")))
            replace_certs = st.checkbox("資格者証を差し替える")
            new_certs = []
            if replace_certs:
                new_certs = st.file_uploader(
                    "新しい資格者証 最大4枚",
                    type=["jpg", "jpeg", "png", "webp", "heic"],
                    accept_multiple_files=True,
                )
                if new_certs and len(new_certs) > 4:
                    new_certs = new_certs[:4]

            c1, c2 = st.columns(2)
            if c1.button("点検者情報を更新", use_container_width=True):
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
        df = get_forklifts(True)
        if df.empty:
            st.warning("登録フォークリフトはありません。")
            render_quick_forklift_register("qr_empty")
        else:
            selected_no = st.selectbox(
                "QRを作るフォークリフト",
                df["forklift_no"].tolist(),
                format_func=lambda no: f"{no} / {df.loc[df['forklift_no'] == no, 'forklift_name'].iloc[0]}",
            )
            url = qr_url(selected_no)
            png = make_qr_png(url)
            st.code(url)
            st.image(png, caption=url, width=280)
            st.download_button("フォークリフトQRダウンロード", data=png, file_name=f"{selected_no}_QR.png", mime="image/png", use_container_width=True)

            st.markdown("### 管理者用QR")
            admin_png = make_qr_png(admin_url())
            st.code(admin_url())
            st.image(admin_png, caption=admin_url(), width=280)
            st.download_button("管理者QRダウンロード", data=admin_png, file_name="管理者QR.png", mime="image/png", use_container_width=True)


elif menu == "QR印刷台紙":
    st.markdown("## QR印刷台紙")
    if require_admin():
        df = get_forklifts(True)
        if df.empty:
            st.warning("登録フォークリフトはありません。")
            render_quick_forklift_register("qr_print_empty")
            st.stop()

        st.caption(f"発行日：{ja_date(date.today())}")
        cols = st.columns(3)
        for i, (_, row) in enumerate(df.iterrows()):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"### {row['forklift_no']}")
                    st.write(row["forklift_name"])
                    url = qr_url(row["forklift_no"])
                    st.image(make_qr_png(url), width=220)
                    st.caption(url)

        st.divider()
        st.markdown("### 管理者用QR")
        st.image(make_qr_png(admin_url()), width=260)
        st.caption(admin_url())
