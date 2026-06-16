import os, sqlite3
from datetime import datetime, date
from io import BytesIO
import pandas as pd
import qrcode
import streamlit as st

APP_TITLE = "重機・車両 始業前点検"
DB_PATH = "inspection_app.db"
PHOTO_DIR = "uploaded_photos"
os.makedirs(PHOTO_DIR, exist_ok=True)

VEHICLE_TYPES = {
    "forklift": "フォークリフト",
    "wheel_loader": "ホイールローダー",
    "dump": "ダンプ",
    "backhoe": "バックホウ",
    "light_truck": "軽トラ",
    "other": "その他",
}

CHECK_ITEMS = {
    "forklift": ["制動装置・ブレーキの効き","操縦装置・ハンドル操作","荷役装置・油圧装置・油漏れ","フォーク・マスト・チェーンの損傷","タイヤ・ホイール・ナットの緩み","前照灯・方向指示器・警報装置","燃料・バッテリー・充電状態"],
    "wheel_loader": ["ブレーキの効き","クラッチ・走行操作","バケット・アーム・ピンの損傷","油圧装置・油漏れ","タイヤ・ホイール・ナットの緩み","灯火類・警報ブザー・バックブザー","燃料・エンジンオイル・冷却水"],
    "dump": ["ブレーキペダルの踏みしろ・効き","タイヤ空気圧・亀裂・異常摩耗","ホイールナットの緩み","灯火類・方向指示器・反射器","エンジンオイル・冷却水・ブレーキ液","荷台・あおり・ダンプ装置・油漏れ","車検証・自賠責・運行前確認"],
    "backhoe": ["ブレーキ・走行操作","作業装置・ブーム・アーム・バケット","油圧装置・油漏れ","クローラー・足回り","旋回装置","警報装置・灯火類","燃料・エンジンオイル・冷却水"],
    "light_truck": ["ブレーキの効き","タイヤ空気圧・損傷","灯火類・方向指示器","エンジンオイル・冷却水","ワイパー・ウォッシャー","積載物・荷台確認"],
    "other": ["ブレーキ・走行装置","操作装置","油漏れ・水漏れ","タイヤ・足回り","灯火類・警報装置","外観・損傷"],
}

def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    con = connect()
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vehicle_no TEXT UNIQUE NOT NULL,
        vehicle_name TEXT NOT NULL,
        vehicle_type TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS inspections (
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
        photo_path TEXT,
        manager_confirmed INTEGER DEFAULT 0,
        manager_name TEXT,
        manager_confirmed_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS inspection_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inspection_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        status TEXT NOT NULL
    )""")
    con.commit()
    con.close()

def seed():
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM vehicles")
    if cur.fetchone()[0] == 0:
        for no, name, vt in [
            ("FL-001","フォークリフト1号","forklift"),
            ("FL-002","フォークリフト2号","forklift"),
            ("WL-001","ホイールローダー1号","wheel_loader"),
            ("DP-001","ダンプ1号","dump"),
        ]:
            cur.execute("INSERT INTO vehicles(vehicle_no,vehicle_name,vehicle_type,created_at) VALUES(?,?,?,?)",
                        (no,name,vt,datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    con.close()

def get_vehicles(active_only=True):
    con = connect()
    q = "SELECT vehicle_no, vehicle_name, vehicle_type, active FROM vehicles"
    if active_only:
        q += " WHERE active=1"
    q += " ORDER BY vehicle_no"
    df = pd.read_sql_query(q, con)
    con.close()
    return df

def get_inspections(where="", params=()):
    con = connect()
    q = "SELECT * FROM inspections"
    if where:
        q += " WHERE " + where
    q += " ORDER BY inspected_at DESC"
    df = pd.read_sql_query(q, con, params=params)
    con.close()
    return df

def get_items(inspection_id):
    con = connect()
    df = pd.read_sql_query("SELECT item_name, status FROM inspection_items WHERE inspection_id=?",
                           con, params=(inspection_id,))
    con.close()
    return df

def add_vehicle(no, name, vt):
    con = connect()
    try:
        con.execute("INSERT INTO vehicles(vehicle_no,vehicle_name,vehicle_type,created_at) VALUES(?,?,?,?)",
                    (no, name, vt, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()
        return True, "登録しました。"
    except sqlite3.IntegrityError:
        return False, "同じ車両番号が既にあります。"
    finally:
        con.close()

def set_active(no, active):
    con = connect()
    con.execute("UPDATE vehicles SET active=? WHERE vehicle_no=?", (1 if active else 0, no))
    con.commit()
    con.close()

def save_photo(file, vehicle_no):
    if file is None:
        return ""
    ext = os.path.splitext(file.name)[1] or ".jpg"
    path = os.path.join(PHOTO_DIR, f"{vehicle_no}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")
    with open(path, "wb") as f:
        f.write(file.getbuffer())
    return path

def save_inspection(vehicle, inspector, meter, statuses, abnormal_detail, action_detail, photo):
    now = datetime.now()
    result = "使用不可" if any(v == "異常あり" for v in statuses.values()) else "使用可"
    photo_path = save_photo(photo, vehicle["vehicle_no"])
    con = connect()
    cur = con.cursor()
    cur.execute("""INSERT INTO inspections(
        inspected_at,inspection_date,vehicle_no,vehicle_name,vehicle_type,inspector,meter,result,abnormal_detail,action_detail,photo_path)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d"), vehicle["vehicle_no"],
         vehicle["vehicle_name"], vehicle["vehicle_type"], inspector, meter, result, abnormal_detail, action_detail, photo_path))
    inspection_id = cur.lastrowid
    for item, status in statuses.items():
        cur.execute("INSERT INTO inspection_items(inspection_id,item_name,status) VALUES(?,?,?)", (inspection_id, item, status))
    con.commit()
    con.close()

def confirm(inspection_id, manager_name):
    con = connect()
    con.execute("UPDATE inspections SET manager_confirmed=1, manager_name=?, manager_confirmed_at=? WHERE id=?",
                (manager_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inspection_id))
    con.commit()
    con.close()

def qr_png(url):
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

init_db()
seed()

st.set_page_config(page_title=APP_TITLE, page_icon="🚜", layout="wide")
st.title("🚜 重機・車両 始業前点検")
st.caption("SQLite保存 / QR共有 / 写真保存 / 異常一覧 / CSV出力")

menu = st.sidebar.radio("メニュー", ["点検入力", "異常一覧", "履歴・出力", "車両マスター", "QRコード発行", "バックアップ"])

if menu == "点検入力":
    st.subheader("点検入力")
    vehicles = get_vehicles()
    if vehicles.empty:
        st.warning("車両を登録してください。")
        st.stop()

    q_vehicle = st.query_params.get("vehicle", "")
    if isinstance(q_vehicle, list):
        q_vehicle = q_vehicle[0] if q_vehicle else ""
    options = vehicles["vehicle_no"].tolist()
    idx = options.index(q_vehicle) if q_vehicle in options else 0

    selected = st.selectbox("車両", options, index=idx,
        format_func=lambda no: f"{no} / {vehicles.loc[vehicles['vehicle_no']==no,'vehicle_name'].iloc[0]}")
    vehicle = vehicles[vehicles["vehicle_no"] == selected].iloc[0].to_dict()
    vt = vehicle["vehicle_type"]

    c1,c2,c3 = st.columns(3)
    c1.metric("車両番号", vehicle["vehicle_no"])
    c2.metric("車両名", vehicle["vehicle_name"])
    c3.metric("車種", VEHICLE_TYPES.get(vt, vt))

    inspector = st.text_input("点検者名")
    meter = st.text_input("メーター・走行距離・アワーメーター")

    statuses = {}
    st.markdown("### 点検項目")
    for i, item in enumerate(CHECK_ITEMS.get(vt, CHECK_ITEMS["other"])):
        with st.container(border=True):
            st.markdown(f"**{item}**")
            statuses[item] = st.radio("判定", ["良好", "異常あり", "対象外"], horizontal=True, key=f"{selected}_{i}_{item}")

    has_abnormal = any(v == "異常あり" for v in statuses.values())
    abnormal_detail = ""
    action_detail = ""
    photo = None

    if has_abnormal:
        st.error("異常あり：この車両は使用不可で保存されます。")
        abnormal_detail = st.text_area("異常内容 ※必須")
        action_detail = st.text_area("対応内容 ※必須")
        photo = st.file_uploader("写真添付 ※必須", type=["jpg","jpeg","png","heic"])

    st.success("最終判定：使用可") if not has_abnormal else st.error("最終判定：使用不可")

    if st.button("点検記録を保存", type="primary", use_container_width=True):
        if not inspector:
            st.warning("点検者名を入力してください。")
        elif has_abnormal and (not abnormal_detail or not action_detail or photo is None):
            st.warning("異常ありの場合は、異常内容・対応内容・写真添付が必須です。")
        else:
            save_inspection(vehicle, inspector, meter, statuses, abnormal_detail, action_detail, photo)
            st.success("保存しました。")

elif menu == "異常一覧":
    st.subheader("異常一覧")
    df = get_inspections("result=?", ("使用不可",))
    st.metric("異常件数", len(df))
    manager = st.text_input("管理者名")
    if df.empty:
        st.info("異常記録はありません。")
    else:
        for _, row in df.iterrows():
            with st.container(border=True):
                st.markdown(f"### {row['vehicle_no']} / {row['vehicle_name']}")
                st.write(f"日時：{row['inspected_at']}")
                st.write(f"点検者：{row['inspector']}")
                st.error("使用不可")
                st.write(f"異常内容：{row['abnormal_detail']}")
                st.write(f"対応内容：{row['action_detail']}")
                st.dataframe(get_items(row["id"]), use_container_width=True, hide_index=True)
                if row["photo_path"] and os.path.exists(row["photo_path"]):
                    st.image(row["photo_path"], caption="異常写真", width=300)
                if row["manager_confirmed"]:
                    st.success(f"確認済：{row['manager_name']} / {row['manager_confirmed_at']}")
                elif st.button("管理者確認", key=f"c{row['id']}"):
                    if not manager:
                        st.warning("管理者名を入力してください。")
                    else:
                        confirm(row["id"], manager)
                        st.rerun()

elif menu == "履歴・出力":
    st.subheader("履歴・出力")
    c1,c2,c3 = st.columns(3)
    start = c1.date_input("開始日", value=date.today().replace(day=1))
    end = c2.date_input("終了日", value=date.today())
    result_filter = c3.selectbox("判定", ["すべて","使用可","使用不可"])
    where = "inspection_date BETWEEN ? AND ?"
    params = [str(start), str(end)]
    if result_filter != "すべて":
        where += " AND result=?"
        params.append(result_filter)
    df = get_inspections(where, tuple(params))
    st.metric("件数", len(df))
    st.dataframe(df, use_container_width=True, hide_index=True)
    if not df.empty:
        export = df.copy()
        export["点検項目"] = [" / ".join([f"{r['item_name']}:{r['status']}" for _, r in get_items(row["id"]).iterrows()]) for _, row in df.iterrows()]
        st.download_button("CSVダウンロード", data=export.to_csv(index=False).encode("utf-8-sig"),
                           file_name="始業前点検記録.csv", mime="text/csv", use_container_width=True)

elif menu == "車両マスター":
    st.subheader("車両マスター")
    with st.form("add"):
        no = st.text_input("車両番号", placeholder="FL-003")
        name = st.text_input("車両名", placeholder="フォークリフト3号")
        vt = st.selectbox("車種", list(VEHICLE_TYPES.keys()), format_func=lambda x: VEHICLE_TYPES[x])
        if st.form_submit_button("登録", use_container_width=True):
            if not no or not name:
                st.warning("車両番号と車両名を入力してください。")
            else:
                ok, msg = add_vehicle(no, name, vt)
                st.success(msg) if ok else st.error(msg)
    df = get_vehicles(False)
    st.dataframe(df, use_container_width=True, hide_index=True)
    if not df.empty:
        target = st.selectbox("状態変更する車両", df["vehicle_no"].tolist())
        active = st.radio("状態", ["有効","無効"], horizontal=True)
        if st.button("状態更新"):
            set_active(target, active=="有効")
            st.rerun()

elif menu == "QRコード発行":
    st.subheader("QRコード発行")
    base_url = st.text_input("アプリURL", placeholder="https://xxxx.streamlit.app")
    vehicles = get_vehicles()
    if not vehicles.empty:
        selected = st.selectbox("QRを作る車両", vehicles["vehicle_no"].tolist(),
            format_func=lambda no: f"{no} / {vehicles.loc[vehicles['vehicle_no']==no,'vehicle_name'].iloc[0]}")
        if st.button("QRコード作成", type="primary", use_container_width=True):
            if not base_url:
                st.warning("URLを入力してください。")
            else:
                url = base_url.rstrip("/") + f"/?vehicle={selected}"
                png = qr_png(url)
                st.image(png, caption=url, width=280)
                st.download_button("QR画像ダウンロード", data=png, file_name=f"{selected}_QR.png", mime="image/png", use_container_width=True)
        if base_url:
            st.dataframe(pd.DataFrame([{
                "車両番号": r["vehicle_no"],
                "車両名": r["vehicle_name"],
                "QR用URL": base_url.rstrip("/") + f"/?vehicle={r['vehicle_no']}"
            } for _, r in vehicles.iterrows()]), use_container_width=True, hide_index=True)

elif menu == "バックアップ":
    st.subheader("バックアップ")
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            st.download_button("SQLiteデータベースをダウンロード", f.read(), "inspection_app.db", "application/octet-stream", use_container_width=True)
    st.caption("写真は uploaded_photos フォルダに保存されます。Streamlit Cloudでは永続保存に制限があります。")
