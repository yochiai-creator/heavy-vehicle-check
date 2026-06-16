import sqlite3
from datetime import datetime, date, timedelta
from io import BytesIO
import urllib.parse

import pandas as pd
import qrcode
import streamlit as st

st.set_page_config(
    page_title="野田組 車両点検記録",
    page_icon="🚜",
    layout="wide",
)

APP_NAME = "野田組 車両点検記録"
APP_URL = "https://heavy-vehicle-check-ghka28mxhavp4qrjpnkb7b.streamlit.app"
ADMIN_CODE = "1224"
DB_PATH = "vehicle_check.db"
WEEK_JA = ["月", "火", "水", "木", "金", "土", "日"]

VEHICLE_TYPES = {
    "forklift": "フォークリフト",
    "vehicle": "車両",
    "construction": "重機",
    "other": "その他",
}

# 法定始業前点検として最低限に絞った簡素項目
CHECK_ITEMS = {
    "forklift": [
        "制動装置・操縦装置",
        "荷役装置・油圧装置",
        "車輪・タイヤ・外観",
        "警報装置・灯火類",
    ],
    "vehicle": [
        "ブレーキ",
        "タイヤ",
        "灯火類・方向指示器",
        "油漏れ・水漏れ・外観",
    ],
    "construction": [
        "ブレーキ・走行装置",
        "作業装置・油圧装置",
        "足回り・外観",
        "警報装置・灯火類",
    ],
    "other": [
        "ブレーキ・操作装置",
        "作業装置・油圧装置",
        "足回り・外観",
        "警報装置・灯火類",
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
    for col_name, col_type in [
        ("photo2_name", "TEXT"), ("photo2_bytes", "BLOB"),
        ("photo3_name", "TEXT"), ("photo3_bytes", "BLOB"),
        ("photo4_name", "TEXT"), ("photo4_bytes", "BLOB"),
    ]:
        ensure_column(cur, "inspections", col_name, col_type)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspection_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    con.commit()
    con.close()

def seed_vehicles():
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM vehicles")
    if cur.fetchone()[0] == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        next_date = (date.today() + timedelta(days=30)).isoformat()
        samples = [
            ("FL-001", "フォークリフト1号", "forklift"),
            ("FL-002", "フォークリフト2号", "forklift"),
            ("WL-001", "ホイールローダー1号", "construction"),
            ("DP-001", "ダンプ1号", "vehicle"),
            ("BH-001", "バックホウ1号", "construction"),
            ("LT-001", "軽トラ1号", "vehicle"),
        ]
        for no, name, vtype in samples:
            cur.execute(
                """INSERT INTO vehicles(
                    vehicle_no, vehicle_name, vehicle_type, active, use_locked, created_at, next_inspection_date, note
                ) VALUES (?, ?, ?, 1, 0, ?, ?, ?)""",
                (no, name, vtype, now, next_date, ""),
            )
    con.commit()
    con.close()

def get_vehicles(active_only=True):
    con = connect()
    query = "SELECT * FROM vehicles"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY vehicle_no"
    df = pd.read_sql_query(query, con)
    con.close()
    return df

def get_vehicle(vehicle_no):
    con = connect()
    df = pd.read_sql_query("SELECT * FROM vehicles WHERE vehicle_no = ?", con, params=(vehicle_no,))
    con.close()
    if df.empty:
        return None
    return df.iloc[0].to_dict()

def add_vehicle(vehicle_no, vehicle_name, vehicle_type, next_inspection_date, note):
    con = connect()
    try:
        con.execute(
            """INSERT INTO vehicles(
                vehicle_no, vehicle_name, vehicle_type, active, use_locked, created_at, next_inspection_date, note
            ) VALUES (?, ?, ?, 1, 0, ?, ?, ?)""",
            (
                vehicle_no.strip(),
                vehicle_name.strip(),
                vehicle_type,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                next_inspection_date.isoformat(),
                note,
            ),
        )
        con.commit()
        return True, "車両を登録しました。"
    except sqlite3.IntegrityError:
        return False, "同じ車両番号が既にあります。"
    finally:
        con.close()

def update_vehicle(vehicle_no, vehicle_name, vehicle_type, active, next_inspection_date, note):
    con = connect()
    con.execute(
        """UPDATE vehicles
           SET vehicle_name=?, vehicle_type=?, active=?, next_inspection_date=?, note=?
           WHERE vehicle_no=?""",
        (vehicle_name, vehicle_type, 1 if active else 0, next_inspection_date.isoformat(), note, vehicle_no),
    )
    con.commit()
    con.close()

def reset_vehicle_lock(vehicle_no):
    con = connect()
    con.execute("UPDATE vehicles SET use_locked = 0 WHERE vehicle_no = ?", (vehicle_no,))
    con.commit()
    con.close()

def save_inspection(vehicle, inspection_date, inspector, meter, statuses, abnormal_detail, action_detail, photos):
    now = datetime.now()
    has_abnormal = any(v == "異常あり" for v in statuses.values())
    result = "使用不可" if has_abnormal else "使用可"

    photo_data = []
    for p in (photos or [])[:4]:
        photo_data.append((p.name, p.getvalue()))
    while len(photo_data) < 4:
        photo_data.append(("", None))

    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO inspections(
            inspected_at, inspection_date, vehicle_no, vehicle_name, vehicle_type,
            inspector, meter, result, abnormal_detail, action_detail,
            photo_name, photo_bytes, photo2_name, photo2_bytes,
            photo3_name, photo3_bytes, photo4_name, photo4_bytes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now.strftime("%Y-%m-%d %H:%M:%S"), inspection_date.isoformat(),
            vehicle["vehicle_no"], vehicle["vehicle_name"], vehicle["vehicle_type"],
            inspector, meter, result, abnormal_detail, action_detail,
            photo_data[0][0], photo_data[0][1],
            photo_data[1][0], photo_data[1][1],
            photo_data[2][0], photo_data[2][1],
            photo_data[3][0], photo_data[3][1],
        ),
    )
    inspection_id = cur.lastrowid
    for item, status in statuses.items():
        cur.execute(
            "INSERT INTO inspection_items(inspection_id, item_name, status) VALUES (?, ?, ?)",
            (inspection_id, item, status),
        )
    if has_abnormal:
        cur.execute("UPDATE vehicles SET use_locked = 1 WHERE vehicle_no = ?", (vehicle["vehicle_no"],))
    con.commit()
    con.close()

def get_inspections(where="", params=()):
    con = connect()
    query = "SELECT * FROM inspections"
    if where:
        query += " WHERE " + where
    query += " ORDER BY inspection_date DESC, inspected_at DESC"
    df = pd.read_sql_query(query, con, params=params)
    con.close()
    return df

def get_items(inspection_id):
    con = connect()
    df = pd.read_sql_query(
        "SELECT item_name, status FROM inspection_items WHERE inspection_id = ?",
        con,
        params=(inspection_id,),
    )
    con.close()
    return df

def confirm_inspection(inspection_id, vehicle_no, manager_name):
    con = connect()
    con.execute(
        """UPDATE inspections
           SET manager_confirmed = 1, manager_name = ?, manager_confirmed_at = ?
           WHERE id = ?""",
        (manager_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inspection_id),
    )
    con.execute("UPDATE vehicles SET use_locked = 0 WHERE vehicle_no = ?", (vehicle_no,))
    con.commit()
    con.close()

def update_inspection_date(inspection_id, new_date):
    con = connect()
    con.execute("UPDATE inspections SET inspection_date=? WHERE id=?", (new_date.isoformat(), inspection_id))
    con.commit()
    con.close()

def make_qr_png(url):
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def qr_url(vehicle_no):
    # QRには車両番号だけを入れる。日本語は入れない。
    return APP_URL.rstrip("/") + f"/?vehicle={urllib.parse.quote(str(vehicle_no), safe='')}"

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

def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")

def parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None

def render_photos(row, width=170):
    cols = st.columns(4)
    pairs = [
        ("photo_name", "photo_bytes"),
        ("photo2_name", "photo2_bytes"),
        ("photo3_name", "photo3_bytes"),
        ("photo4_name", "photo4_bytes"),
    ]
    shown = False
    for idx, (name_col, bytes_col) in enumerate(pairs):
        if bytes_col in row.index and row[bytes_col] is not None:
            with cols[idx]:
                st.image(row[bytes_col], caption=row.get(name_col, ""), width=width)
            shown = True
    if not shown:
        st.caption("写真なし")

def today_unchecked():
    vehicles = get_vehicles(active_only=True)
    checked = get_inspections("inspection_date = ?", (date.today().isoformat(),))
    checked_set = set(checked["vehicle_no"].tolist()) if not checked.empty else set()
    if vehicles.empty:
        return pd.DataFrame()
    return vehicles[~vehicles["vehicle_no"].isin(checked_set)][["vehicle_no", "vehicle_name", "vehicle_type", "use_locked"]]

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

init_db()
seed_vehicles()

st.markdown("""
<style>
.block-container { padding-top: 1rem; max-width: 1120px; }
div.stButton > button { border-radius: 10px; font-weight: 700; }
[data-testid="stMetricValue"] { font-size: 24px; }
h1, h2, h3 { line-height: 1.25; }
@media print {
  section[data-testid="stSidebar"], header, footer, .stButton { display:none !important; }
}
</style>
""", unsafe_allow_html=True)

st.title("🚜 野田組 車両点検記録")
st.caption("日常点検・運行前点検記録システム")

query_vehicle = get_query_value("vehicle")
query_admin = get_query_value("admin") == "true"
vehicles_all = get_vehicles(active_only=True)
valid_vehicle_nos = set(vehicles_all["vehicle_no"].tolist()) if not vehicles_all.empty else set()

if query_vehicle and query_vehicle in valid_vehicle_nos:
    st.success(f"QRコードから車両を固定しました：{query_vehicle}")
elif query_vehicle and query_vehicle not in valid_vehicle_nos:
    st.warning("QRコードの車両番号が車両マスターにありません。車両を選択してください。")
    query_vehicle = ""

if query_admin:
    st.info("管理者QRからアクセスしています。")

alerts = inspection_alerts()
if not alerts.empty:
    st.warning("次回点検日が近い、または期限切れの車両があります。")
    st.table(alerts)

default_menu = "管理者メニュー" if query_admin else "点検入力"
menu_options = ["点検入力", "管理者メニュー", "異常一覧", "履歴・出力", "車両マスター", "QRコード発行", "QR印刷台紙"]
menu = st.sidebar.radio("メニュー", menu_options, index=menu_options.index(default_menu))

if menu == "点検入力":
    st.markdown("## 点検入力")

    vehicles = get_vehicles(active_only=True)
    if vehicles.empty:
        st.warning("車両マスターに車両を登録してください。")
        st.stop()

    options = vehicles["vehicle_no"].tolist()

    if query_vehicle and query_vehicle in options:
        selected_no = query_vehicle
        selected_label = vehicles.loc[vehicles["vehicle_no"] == selected_no, "vehicle_name"].iloc[0]
        st.info(f"車両固定：{selected_no} / {selected_label}")
    else:
        selected_no = st.selectbox(
            "車両",
            options,
            format_func=lambda no: f"{no} / {vehicles.loc[vehicles['vehicle_no'] == no, 'vehicle_name'].iloc[0]}",
        )

    vehicle = get_vehicle(selected_no)
    vehicle_type = vehicle["vehicle_type"]

    c1, c2, c3 = st.columns(3)
    c1.metric("車両番号", vehicle["vehicle_no"])
    c2.metric("車両名", vehicle["vehicle_name"])
    c3.metric("区分", VEHICLE_TYPES.get(vehicle_type, vehicle_type))

    inspection_date = st.date_input("点検日", value=date.today())
    st.caption(f"点検日：{ja_date(inspection_date)}")

    if vehicle.get("use_locked", 0):
        st.error("この車両は異常報告により使用禁止中です。管理者確認まで使用しないでください。")

    inspector = st.text_input("点検者名", placeholder="氏名")
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

    st.error("最終判定：使用不可") if has_abnormal else st.success("最終判定：使用可")

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
        unconfirmed = abnormal[abnormal["manager_confirmed"] == 0] if not abnormal.empty else pd.DataFrame()

        c1, c2, c3 = st.columns(3)
        c1.metric("本日未点検", len(unchecked))
        c2.metric("異常件数", len(abnormal))
        c3.metric("未承認異常", len(unconfirmed))

        st.markdown("### 本日未点検一覧")
        if unchecked.empty:
            st.success("本日の未点検車両はありません。")
        else:
            jp = unchecked.rename(columns={"vehicle_no": "車両番号", "vehicle_name": "車両名", "vehicle_type": "区分", "use_locked": "使用禁止"})
            jp["区分"] = jp["区分"].map(VEHICLE_TYPES)
            jp["使用禁止"] = jp["使用禁止"].apply(lambda x: "使用禁止" if x else "")
            st.table(jp)

        st.markdown("### 管理者QR")
        admin_png = make_qr_png(admin_url())
        st.image(admin_png, caption=admin_url(), width=260)
        st.download_button("管理者QRダウンロード", data=admin_png, file_name="管理者QR.png", mime="image/png")

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
                    st.write("写真")
                    render_photos(row)
                    st.write("点検項目")
                    st.table(get_items(row["id"]).rename(columns={"item_name": "点検項目", "status": "判定"}))
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
                    c1.write(f"**点検日**\n{ja_date(d)}")
                    c2.write(f"**車両**\n{row['vehicle_no']} / {row['vehicle_name']}")
                    c3.write(f"**点検者**\n{row['inspector']}")
                    c4.error("使用不可") if row["result"] == "使用不可" else c4.success("使用可")
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

            export_df = df.drop(columns=["photo_bytes", "photo2_bytes", "photo3_bytes", "photo4_bytes"], errors="ignore").copy()
            export_df = export_df.rename(columns={
                "id": "ID", "inspected_at": "保存日時", "inspection_date": "点検日",
                "vehicle_no": "車両番号", "vehicle_name": "車両名", "vehicle_type": "区分",
                "inspector": "点検者", "meter": "メーター", "result": "判定",
                "abnormal_detail": "異常内容", "action_detail": "対応内容",
                "photo_name": "写真1", "photo2_name": "写真2", "photo3_name": "写真3", "photo4_name": "写真4",
                "manager_confirmed": "管理者確認", "manager_name": "管理者名", "manager_confirmed_at": "管理者確認日時",
            })
            if "区分" in export_df.columns:
                export_df["区分"] = export_df["区分"].map(VEHICLE_TYPES)
            if "管理者確認" in export_df.columns:
                export_df["管理者確認"] = export_df["管理者確認"].apply(lambda x: "確認済" if x else "未確認")

            item_texts = []
            for _, row in df.iterrows():
                items = get_items(row["id"])
                item_texts.append(" / ".join([f"{r['item_name']}:{r['status']}" for _, r in items.iterrows()]))
            export_df["点検項目"] = item_texts

            excel_buf = BytesIO()
            with pd.ExcelWriter(excel_buf, engine="xlsxwriter") as writer:
                export_df.to_excel(writer, index=False, sheet_name="点検履歴")
            st.download_button("Excel出力", data=excel_buf.getvalue(), file_name="野田組_車両点検記録.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            st.download_button("CSV出力", data=csv_bytes(export_df), file_name="野田組_車両点検記録.csv", mime="text/csv", use_container_width=True)

elif menu == "車両マスター":
    st.markdown("## 車両マスター")
    if require_admin():
        with st.form("vehicle_form"):
            st.markdown("### 車両追加")
            vehicle_no = st.text_input("車両番号", placeholder="例：FL-003")
            vehicle_name = st.text_input("車両名", placeholder="例：フォークリフト3号")
            vehicle_type = st.selectbox("区分", list(VEHICLE_TYPES.keys()), format_func=lambda x: VEHICLE_TYPES[x])
            next_inspection_date = st.date_input("次回点検日", value=date.today() + timedelta(days=30))
            st.caption(f"次回点検日：{ja_date(next_inspection_date)}")
            note = st.text_area("備考", placeholder="車検、修理予定、管理メモなど")
            submitted = st.form_submit_button("登録", use_container_width=True)

            if submitted:
                if not vehicle_no or not vehicle_name:
                    st.warning("車両番号と車両名を入力してください。")
                else:
                    ok, msg = add_vehicle(vehicle_no, vehicle_name, vehicle_type, next_inspection_date, note)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

        df = get_vehicles(active_only=False)
        st.markdown("### 登録車両")
        if df.empty:
            st.info("登録車両はありません。")
        else:
            for _, r in df.iterrows():
                with st.container(border=True):
                    d = parse_iso_date(r.get("next_inspection_date", ""))
                    c1, c2, c3, c4 = st.columns(4)
                    c1.write(f"**車両番号**\n{r['vehicle_no']}")
                    c2.write(f"**車両名**\n{r['vehicle_name']}")
                    c3.write(f"**区分**\n{VEHICLE_TYPES.get(r['vehicle_type'], r['vehicle_type'])}")
                    c4.write(f"**状態**\n{'有効' if r['active'] else '無効'}")
                    if d:
                        st.caption(f"次回点検日：{ja_date(d)}")
                    if r.get("use_locked", 0):
                        st.error("使用禁止中")
                    if r.get("note"):
                        st.write(f"備考：{r['note']}")

            st.markdown("### 車両情報の編集")
            target = st.selectbox("編集する車両", df["vehicle_no"].tolist())
            row = df[df["vehicle_no"] == target].iloc[0]
            new_name = st.text_input("車両名", value=row["vehicle_name"])
            new_type = st.selectbox("区分", list(VEHICLE_TYPES.keys()), index=list(VEHICLE_TYPES.keys()).index(row["vehicle_type"]), format_func=lambda x: VEHICLE_TYPES[x])
            old_next = parse_iso_date(row.get("next_inspection_date", ""))
            new_next = st.date_input("次回点検日", value=old_next or date.today())
            st.caption(f"次回点検日：{ja_date(new_next)}")
            new_note = st.text_area("備考", value=row.get("note", "") or "")
            new_active = st.radio("状態", ["有効", "無効"], index=0 if row["active"] else 1, horizontal=True)
            c1, c2 = st.columns(2)
            if c1.button("車両情報を更新", use_container_width=True):
                update_vehicle(target, new_name, new_type, new_active == "有効", new_next, new_note)
                st.success("更新しました。")
                st.rerun()
            if c2.button("使用禁止を手動解除", use_container_width=True):
                reset_vehicle_lock(target)
                st.success("使用禁止を解除しました。")
                st.rerun()

elif menu == "QRコード発行":
    st.markdown("## QRコード発行")
    if require_admin():
        st.info("アプリURLは固定済みです。URL入力は不要です。")
        vehicles = get_vehicles(active_only=True)
        if vehicles.empty:
            st.warning("車両マスターに車両を登録してください。")
        else:
            selected_no = st.selectbox("QRを作る車両", vehicles["vehicle_no"].tolist(), format_func=lambda no: f"{no} / {vehicles.loc[vehicles['vehicle_no'] == no, 'vehicle_name'].iloc[0]}")
            url = qr_url(selected_no)
            st.code(url)
            png = make_qr_png(url)
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
        vehicles = get_vehicles(active_only=True)
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
