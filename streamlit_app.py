import sqlite3
from datetime import datetime, date
from io import BytesIO
import pandas as pd
import qrcode
import streamlit as st

st.set_page_config(
    page_title="野田組 重機・車両 始業前点検",
    page_icon="🚜",
    layout="wide",
)

APP_URL = "https://heavy-vehicle-check-ghka28mxhavp4qrjpnkb7b.streamlit.app"
DB_PATH = "vehicle_check.db"

VEHICLE_TYPES = {
    "forklift": "フォークリフト",
    "wheel_loader": "ホイールローダー",
    "dump": "ダンプ",
    "backhoe": "バックホウ",
    "light_truck": "軽トラ",
    "other": "その他",
}

CHECK_ITEMS = {
    "forklift": [
        "制動装置・ブレーキの効き",
        "操縦装置・ハンドル操作",
        "荷役装置・油圧装置・油漏れ",
        "フォーク・マスト・チェーンの損傷",
        "タイヤ・ホイール・ナットの緩み",
        "前照灯・方向指示器・警報装置",
        "燃料・バッテリー・充電状態",
    ],
    "wheel_loader": [
        "ブレーキの効き",
        "クラッチ・走行操作",
        "バケット・アーム・ピンの損傷",
        "油圧装置・油漏れ",
        "タイヤ・ホイール・ナットの緩み",
        "灯火類・警報ブザー・バックブザー",
        "燃料・エンジンオイル・冷却水",
    ],
    "dump": [
        "ブレーキペダルの踏みしろ・効き",
        "タイヤ空気圧・亀裂・異常摩耗",
        "ホイールナットの緩み",
        "灯火類・方向指示器・反射器",
        "エンジンオイル・冷却水・ブレーキ液",
        "荷台・あおり・ダンプ装置・油漏れ",
        "車検証・自賠責・運行前確認",
    ],
    "backhoe": [
        "ブレーキ・走行操作",
        "作業装置・ブーム・アーム・バケット",
        "油圧装置・油漏れ",
        "クローラー・足回り",
        "旋回装置",
        "警報装置・灯火類",
        "燃料・エンジンオイル・冷却水",
    ],
    "light_truck": [
        "ブレーキの効き",
        "タイヤ空気圧・損傷",
        "灯火類・方向指示器",
        "エンジンオイル・冷却水",
        "ワイパー・ウォッシャー",
        "積載物・荷台確認",
    ],
    "other": [
        "ブレーキ・走行装置",
        "操作装置",
        "油漏れ・水漏れ",
        "タイヤ・足回り",
        "灯火類・警報装置",
        "外観・損傷",
    ],
}

def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

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
            manager_confirmed INTEGER DEFAULT 0,
            manager_name TEXT,
            manager_confirmed_at TEXT
        )
    """)
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
        samples = [
            ("FL-001", "フォークリフト1号", "forklift"),
            ("FL-002", "フォークリフト2号", "forklift"),
            ("WL-001", "ホイールローダー1号", "wheel_loader"),
            ("DP-001", "ダンプ1号", "dump"),
            ("BH-001", "バックホウ1号", "backhoe"),
            ("LT-001", "軽トラ1号", "light_truck"),
        ]
        for no, name, vtype in samples:
            cur.execute(
                "INSERT INTO vehicles(vehicle_no, vehicle_name, vehicle_type, created_at) VALUES (?, ?, ?, ?)",
                (no, name, vtype, now),
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

def add_vehicle(vehicle_no, vehicle_name, vehicle_type):
    con = connect()
    try:
        con.execute(
            "INSERT INTO vehicles(vehicle_no, vehicle_name, vehicle_type, created_at) VALUES (?, ?, ?, ?)",
            (vehicle_no, vehicle_name, vehicle_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        con.commit()
        return True, "車両を登録しました。"
    except sqlite3.IntegrityError:
        return False, "同じ車両番号が既にあります。"
    finally:
        con.close()

def update_vehicle(vehicle_no, vehicle_name, vehicle_type, active):
    con = connect()
    con.execute(
        "UPDATE vehicles SET vehicle_name=?, vehicle_type=?, active=? WHERE vehicle_no=?",
        (vehicle_name, vehicle_type, 1 if active else 0, vehicle_no),
    )
    con.commit()
    con.close()

def reset_vehicle_lock(vehicle_no):
    con = connect()
    con.execute("UPDATE vehicles SET use_locked=0 WHERE vehicle_no=?", (vehicle_no,))
    con.commit()
    con.close()

def save_inspection(vehicle, inspector, meter, statuses, abnormal_detail, action_detail, photo):
    now = datetime.now()
    has_abnormal = any(v == "異常あり" for v in statuses.values())
    result = "使用不可" if has_abnormal else "使用可"
    photo_name = ""
    photo_bytes = None
    if photo is not None:
        photo_name = photo.name
        photo_bytes = photo.getvalue()

    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO inspections(
            inspected_at, inspection_date, vehicle_no, vehicle_name, vehicle_type,
            inspector, meter, result, abnormal_detail, action_detail,
            photo_name, photo_bytes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d"),
            vehicle["vehicle_no"],
            vehicle["vehicle_name"],
            vehicle["vehicle_type"],
            inspector,
            meter,
            result,
            abnormal_detail,
            action_detail,
            photo_name,
            photo_bytes,
        ),
    )
    inspection_id = cur.lastrowid

    for item, status in statuses.items():
        cur.execute(
            "INSERT INTO inspection_items(inspection_id, item_name, status) VALUES (?, ?, ?)",
            (inspection_id, item, status),
        )

    if has_abnormal:
        cur.execute("UPDATE vehicles SET use_locked=1 WHERE vehicle_no=?", (vehicle["vehicle_no"],))

    con.commit()
    con.close()
    return inspection_id

def get_inspections(where="", params=()):
    con = connect()
    query = "SELECT * FROM inspections"
    if where:
        query += " WHERE " + where
    query += " ORDER BY inspected_at DESC"
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
        """
        UPDATE inspections
        SET manager_confirmed=1, manager_name=?, manager_confirmed_at=?
        WHERE id=?
        """,
        (manager_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inspection_id),
    )
    con.execute("UPDATE vehicles SET use_locked=0 WHERE vehicle_no=?", (vehicle_no,))
    con.commit()
    con.close()

def make_qr_png(url):
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def qr_url(vehicle_no):
    return APP_URL.rstrip("/") + f"/?vehicle={vehicle_no}"

def get_query_vehicle():
    try:
        value = st.query_params.get("vehicle", "")
    except Exception:
        return ""
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""

def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")

init_db()
seed_vehicles()

st.markdown("""
<style>
.block-container { padding-top: 1rem; max-width: 1100px; }
div.stButton > button { border-radius: 10px; font-weight: 700; }
[data-testid="stMetricValue"] { font-size: 24px; }
@media print {
  section[data-testid="stSidebar"], header, footer, .stButton { display:none !important; }
}
</style>
""", unsafe_allow_html=True)

st.title("🚜 野田組 重機・車両 始業前点検")
st.caption("URL固定版 / QR一括発行 / SQLite保存 / 写真DB保存 / 管理者確認 / CSV出力")
st.info(f"固定アプリURL：{APP_URL}")

menu = st.sidebar.radio(
    "メニュー",
    ["点検入力", "異常一覧", "履歴・出力", "車両マスター", "QRコード発行", "QR印刷台紙", "バックアップ"],
)

if menu == "点検入力":
    st.header("点検入力")

    vehicles = get_vehicles(active_only=True)
    if vehicles.empty:
        st.warning("車両マスターに車両を登録してください。")
        st.stop()

    query_vehicle = get_query_vehicle()
    options = vehicles["vehicle_no"].tolist()

    default_index = 0
    if query_vehicle in options:
        default_index = options.index(query_vehicle)
        st.success(f"QRコードから車両を自動選択しました：{query_vehicle}")

    selected_no = st.selectbox(
        "車両",
        options,
        index=default_index,
        format_func=lambda no: f"{no} / {vehicles.loc[vehicles['vehicle_no'] == no, 'vehicle_name'].iloc[0]}",
    )

    vehicle = get_vehicle(selected_no)
    vehicle_type = vehicle["vehicle_type"]

    col1, col2, col3 = st.columns(3)
    col1.metric("車両番号", vehicle["vehicle_no"])
    col2.metric("車両名", vehicle["vehicle_name"])
    col3.metric("車種", VEHICLE_TYPES.get(vehicle_type, vehicle_type))

    if vehicle.get("use_locked", 0):
        st.error("この車両は異常報告により使用禁止中です。管理者確認まで使用しないでください。")

    inspector = st.text_input("点検者名", placeholder="氏名")
    meter = st.text_input("メーター・走行距離・アワーメーター", placeholder="例：1234h / 56000km")

    st.subheader("点検項目")
    statuses = {}
    for i, item in enumerate(CHECK_ITEMS.get(vehicle_type, CHECK_ITEMS["other"])):
        with st.container(border=True):
            st.markdown(f"**{item}**")
            statuses[item] = st.radio(
                "判定",
                ["良好", "異常あり", "対象外"],
                horizontal=True,
                key=f"{selected_no}_{i}_{item}",
            )

    has_abnormal = any(v == "異常あり" for v in statuses.values())
    abnormal_detail = ""
    action_detail = ""
    photo = None

    if has_abnormal:
        st.error("異常あり：この車両は使用不可として保存されます。")
        abnormal_detail = st.text_area("異常内容 ※必須", placeholder="どこが、どう悪いか")
        action_detail = st.text_area("対応内容 ※必須", placeholder="使用停止、修理依頼、管理者報告など")
        photo = st.file_uploader("写真添付 ※必須", type=["jpg", "jpeg", "png", "webp", "heic"])

    if has_abnormal:
        st.error("最終判定：使用不可")
    else:
        st.success("最終判定：使用可")

    if st.button("点検記録を保存", type="primary", use_container_width=True):
        if not inspector:
            st.warning("点検者名を入力してください。")
        elif has_abnormal and (not abnormal_detail or not action_detail or photo is None):
            st.warning("異常ありの場合は、異常内容・対応内容・写真添付が必須です。")
        else:
            save_inspection(vehicle, inspector, meter, statuses, abnormal_detail, action_detail, photo)
            st.success("点検記録を保存しました。")
            st.balloons()

elif menu == "異常一覧":
    st.header("異常一覧")

    df = get_inspections("result = ?", ("使用不可",))
    unconfirmed = df[df["manager_confirmed"] == 0] if not df.empty else pd.DataFrame()

    col1, col2 = st.columns(2)
    col1.metric("異常件数", len(df))
    col2.metric("未確認", len(unconfirmed))

    manager_name = st.text_input("管理者名", placeholder="管理者確認に使用")

    if df.empty:
        st.info("異常記録はありません。")
    else:
        for _, row in df.iterrows():
            with st.container(border=True):
                st.subheader(f"{row['vehicle_no']} / {row['vehicle_name']}")
                st.write(f"日時：{row['inspected_at']}")
                st.write(f"点検者：{row['inspector']}")
                st.error("使用不可")
                st.write(f"異常内容：{row['abnormal_detail']}")
                st.write(f"対応内容：{row['action_detail']}")

                items = get_items(row["id"])
                st.dataframe(items, use_container_width=True, hide_index=True)

                if row["photo_bytes"] is not None:
                    st.image(row["photo_bytes"], caption=row["photo_name"], width=320)

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
    st.header("履歴・出力")

    col1, col2, col3 = st.columns(3)
    start = col1.date_input("開始日", value=date.today().replace(day=1))
    end = col2.date_input("終了日", value=date.today())
    result_filter = col3.selectbox("判定", ["すべて", "使用可", "使用不可"])

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
        view_df = df.drop(columns=["photo_bytes"], errors="ignore")
        st.dataframe(view_df, use_container_width=True, hide_index=True)

        export_df = view_df.copy()
        item_texts = []
        for _, row in df.iterrows():
            items = get_items(row["id"])
            item_texts.append(" / ".join([f"{r['item_name']}:{r['status']}" for _, r in items.iterrows()]))
        export_df["点検項目"] = item_texts

        st.download_button(
            "CSVダウンロード",
            data=csv_bytes(export_df),
            file_name="始業前点検記録.csv",
            mime="text/csv",
            use_container_width=True,
        )

elif menu == "車両マスター":
    st.header("車両マスター")

    with st.form("vehicle_form"):
        st.subheader("車両追加")
        vehicle_no = st.text_input("車両番号", placeholder="例：FL-003")
        vehicle_name = st.text_input("車両名", placeholder="例：フォークリフト3号")
        vehicle_type = st.selectbox("車種", list(VEHICLE_TYPES.keys()), format_func=lambda x: VEHICLE_TYPES[x])
        submitted = st.form_submit_button("登録", use_container_width=True)

        if submitted:
            if not vehicle_no or not vehicle_name:
                st.warning("車両番号と車両名を入力してください。")
            else:
                ok, msg = add_vehicle(vehicle_no, vehicle_name, vehicle_type)
                st.success(msg) if ok else st.error(msg)

    df = get_vehicles(active_only=False)
    st.subheader("登録車両")
    st.dataframe(df, use_container_width=True, hide_index=True)

    if not df.empty:
        st.subheader("車両情報の編集")
        target = st.selectbox("編集する車両", df["vehicle_no"].tolist())
        row = df[df["vehicle_no"] == target].iloc[0]
        new_name = st.text_input("車両名", value=row["vehicle_name"])
        new_type = st.selectbox(
            "車種",
            list(VEHICLE_TYPES.keys()),
            index=list(VEHICLE_TYPES.keys()).index(row["vehicle_type"]),
            format_func=lambda x: VEHICLE_TYPES[x],
        )
        new_active = st.radio("状態", ["有効", "無効"], index=0 if row["active"] else 1, horizontal=True)

        c1, c2 = st.columns(2)
        if c1.button("車両情報を更新", use_container_width=True):
            update_vehicle(target, new_name, new_type, new_active == "有効")
            st.success("更新しました。")
            st.rerun()

        if c2.button("使用禁止を手動解除", use_container_width=True):
            reset_vehicle_lock(target)
            st.success("使用禁止を解除しました。")
            st.rerun()

elif menu == "QRコード発行":
    st.header("QRコード発行")
    st.info("アプリURLは固定済みです。URL入力は不要です。")

    vehicles = get_vehicles(active_only=True)
    if vehicles.empty:
        st.warning("車両マスターに車両を登録してください。")
    else:
        selected_no = st.selectbox(
            "QRを作る車両",
            vehicles["vehicle_no"].tolist(),
            format_func=lambda no: f"{no} / {vehicles.loc[vehicles['vehicle_no'] == no, 'vehicle_name'].iloc[0]}",
        )

        url = qr_url(selected_no)
        st.code(url)

        png = make_qr_png(url)
        st.image(png, caption=url, width=280)
        st.download_button(
            "QR画像ダウンロード",
            data=png,
            file_name=f"{selected_no}_QR.png",
            mime="image/png",
            use_container_width=True,
        )

elif menu == "QR印刷台紙":
    st.header("QR印刷台紙")
    st.info("全車両のQRを一覧表示します。ブラウザの印刷機能でPDF保存・印刷できます。")

    if st.button("印刷 / PDF保存"):
        st.warning("ブラウザのメニューから印刷、または Ctrl + P でPDF保存してください。")

    vehicles = get_vehicles(active_only=True)

    if vehicles.empty:
        st.warning("車両マスターに車両を登録してください。")
    else:
        cols = st.columns(3)
        for i, (_, row) in enumerate(vehicles.iterrows()):
            with cols[i % 3]:
                with st.container(border=True):
                    st.subheader(row["vehicle_no"])
                    st.write(row["vehicle_name"])
                    st.caption(VEHICLE_TYPES.get(row["vehicle_type"], row["vehicle_type"]))
                    url = qr_url(row["vehicle_no"])
                    st.image(make_qr_png(url), width=220)
                    st.caption(url)

elif menu == "バックアップ":
    st.header("バックアップ")

    with open(DB_PATH, "rb") as f:
        st.download_button(
            "SQLiteデータベースをダウンロード",
            data=f.read(),
            file_name="vehicle_check.db",
            mime="application/octet-stream",
            use_container_width=True,
        )

    st.warning("Streamlit Cloudは無料環境だとDBが消える可能性があります。本格運用は定期バックアップしてください。")
