
import os
import sqlite3
import urllib.parse
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
import qrcode
import streamlit as st

st.set_page_config(page_title="野田組 フォークリフト始業前点検", page_icon="🚜", layout="wide")

APP_URL = "https://heavy-vehicle-check-ghka28mxhavp4qrjpnkb7b.streamlit.app"
ADMIN_CODE = "1224"
DB_PATH = "forklift_check.db"
WEEK_JA = ["月", "火", "水", "木", "金", "土", "日"]
RETENTION_DAYS = 1095

CHECK_ITEMS = {
    "走行装置": ["ブレーキ", "駐車ブレーキ", "ハンドル・操舵装置", "タイヤ・ホイール"],
    "荷役装置": ["フォーク損傷", "フォーク固定ピン", "バックレスト", "マスト損傷", "リフトチェーン張り", "リフトチェーン給油状態", "荷重計（装備車のみ）"],
    "油圧装置": ["リフトシリンダー損傷", "チルトシリンダー損傷", "油圧ホース", "油漏れ"],
    "安全装置": ["ヘッドガード", "シートベルト", "ライト", "バックブザー", "ホーン", "ミラー"],
    "エンジン・電源": ["バッテリー", "燃料", "エンジンオイル", "冷却水"],
    "外観": ["車体損傷", "ボルト・ナット緩み", "異物付着"],
}

def clean_text(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    s = str(v)
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
    # 自動初期登録はしない。
    # 全車両削除後にFL-001/FL-002が復活するのを防ぐ。
    pass

def add_sample_forklifts():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nd = (date.today() + timedelta(days=30)).isoformat()
    con = connect()
    cur = con.cursor()
    added = 0
    for no, name in [("FL-001", "フォークリフト1号"), ("FL-002", "フォークリフト2号")]:
        try:
            cur.execute(
                "INSERT INTO forklifts(forklift_no, forklift_name, active, use_locked, next_inspection_date, note, created_at) VALUES (?, ?, 1, 0, ?, '', ?)",
                (no, name, nd, now),
            )
            added += 1
        except sqlite3.IntegrityError:
            pass
    con.commit()
    con.close()
    return added

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

def get_forklift(no):
    con = connect()
    df = pd.read_sql_query("SELECT * FROM forklifts WHERE forklift_no=?", con, params=(clean_text(no),))
    con.close()
    if df.empty:
        return None
    return df.iloc[0].to_dict()

def add_forklift(no, name, next_date, note):
    con = connect()
    try:
        con.execute(
            "INSERT INTO forklifts(forklift_no, forklift_name, active, use_locked, next_inspection_date, note, created_at) VALUES (?, ?, 1, 0, ?, ?, ?)",
            (clean_text(no), clean_text(name), next_date.isoformat(), clean_text(note), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        con.commit()
        return True, "登録しました。"
    except sqlite3.IntegrityError:
        return False, "同じ車両番号が既にあります。"
    finally:
        con.close()

def update_forklift(no, name, active, next_date, note):
    con = connect()
    con.execute(
        "UPDATE forklifts SET forklift_name=?, active=?, next_inspection_date=?, note=? WHERE forklift_no=?",
        (clean_text(name), 1 if active else 0, next_date.isoformat(), clean_text(note), clean_text(no)),
    )
    con.commit()
    con.close()

def delete_forklift(no):
    con = connect()
    cur = con.cursor()
    cur.execute("DELETE FROM forklifts WHERE forklift_no=?", (clean_text(no),))
    deleted = cur.rowcount
    con.commit()
    con.close()
    return deleted

def reset_forklift_lock(no):
    con = connect()
    con.execute("UPDATE forklifts SET use_locked=0 WHERE forklift_no=?", (clean_text(no),))
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
        for col in ["inspector_name", "note"]:
            if col in df.columns:
                df[col] = df[col].apply(clean_text)
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
            """INSERT INTO inspectors(
                inspector_name, active, note,
                cert1_name, cert1_bytes, cert2_name, cert2_bytes,
                cert3_name, cert3_bytes, cert4_name, cert4_bytes, created_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                clean_text(name), clean_text(note),
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

def delete_inspector(inspector_id):
    con = connect()
    con.execute("DELETE FROM inspectors WHERE id=?", (inspector_id,))
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
    df = pd.read_sql_query("SELECT category, item_name, status FROM inspection_items WHERE inspection_id=?", con, params=(inspection_id,))
    con.close()
    return df

def get_today_inspection(no):
    df = get_inspections("forklift_no=? AND inspection_date=?", (clean_text(no), date.today().isoformat()))
    if df.empty:
        return None
    return df.iloc[0]

def save_inspection(forklift, inspection_date, inspector, meter, statuses, abnormal_detail, action_detail, photos):
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
        """INSERT INTO inspections(
            inspected_at, inspection_date, forklift_no, forklift_name, inspector, meter, result,
            abnormal_detail, action_detail, photo1_name, photo1_bytes, photo2_name, photo2_bytes,
            photo3_name, photo3_bytes, photo4_name, photo4_bytes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
        cur.execute("UPDATE forklifts SET use_locked=1 WHERE forklift_no=?", (forklift["forklift_no"],))
    con.commit()
    con.close()

def confirm_inspection(inspection_id, forklift_no, manager_name):
    con = connect()
    con.execute(
        "UPDATE inspections SET manager_confirmed=1, manager_name=?, manager_confirmed_at=? WHERE id=?",
        (clean_text(manager_name), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inspection_id),
    )
    con.execute("UPDATE forklifts SET use_locked=0 WHERE forklift_no=?", (clean_text(forklift_no),))
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

def make_qr_png(url):
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def qr_url(no):
    return APP_URL.rstrip("/") + "/?forklift=" + urllib.parse.quote(str(no), safe="")

def admin_url():
    return APP_URL.rstrip("/") + "/?admin=true"

def query_value(key):
    try:
        v = st.query_params.get(key, "")
    except Exception:
        return ""
    if isinstance(v, list):
        v = v[0] if v else ""
    return urllib.parse.unquote(str(v or ""))

def parse_date(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except Exception:
        return None

def render_photos(row, width=160):
    pairs = [("photo1_name", "photo1_bytes"), ("photo2_name", "photo2_bytes"), ("photo3_name", "photo3_bytes"), ("photo4_name", "photo4_bytes")]
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
    pairs = [("cert1_name", "cert1_bytes"), ("cert2_name", "cert2_bytes"), ("cert3_name", "cert3_bytes"), ("cert4_name", "cert4_bytes")]
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
    checked = get_inspections("inspection_date=?", (date.today().isoformat(),))
    checked_set = set(checked["forklift_no"].tolist()) if not checked.empty else set()
    if forklifts.empty:
        return pd.DataFrame()
    return forklifts[~forklifts["forklift_no"].isin(checked_set)]

def system_checks():
    errors = []
    warnings = []
    forklifts = get_forklifts(True)
    inspectors = get_inspectors(True)
    abnormal = get_inspections("result=?", ("使用不可",))
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
    return errors, warnings

def make_export_df(df):
    out = df.drop(columns=["photo1_bytes", "photo2_bytes", "photo3_bytes", "photo4_bytes"], errors="ignore").copy()
    out = out.rename(columns={
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
        "manager_confirmed": "管理者確認",
        "manager_name": "管理者名",
        "manager_confirmed_at": "管理者確認日時",
    })
    if "管理者確認" in out.columns:
        out["管理者確認"] = out["管理者確認"].apply(lambda x: "確認済" if x else "未確認")
    item_texts = []
    for _, row in df.iterrows():
        items = get_items(row["id"])
        item_texts.append(" / ".join([f"{r['category']}:{r['item_name']}={r['status']}" for _, r in items.iterrows()]))
    out["点検項目"] = item_texts
    return out

def excel_bytes(df):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="点検履歴")
        ws = writer.sheets["点検履歴"]
        ws.freeze_panes(1, 0)
        for idx, col in enumerate(df.columns):
            width = 60 if col == "点検項目" else 18
            ws.set_column(idx, idx, width)
    return buf.getvalue()

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

def quick_register(prefix):
    st.markdown("### フォークリフト登録")
    if st.button("サンプル車両 FL-001 / FL-002 を追加", key=prefix + "_sample_add", use_container_width=True):
        added = add_sample_forklifts()
        if added > 0:
            st.success(f"{added}台のサンプル車両を追加しました。")
        else:
            st.info("サンプル車両は既に登録済みです。")
        st.rerun()
    with st.form(prefix + "_register_form"):
        no = st.text_input("車両番号", placeholder="FL-001", key=prefix + "_no")
        name = st.text_input("車両名", placeholder="フォークリフト1号", key=prefix + "_name")
        next_date = st.date_input("次回点検日", value=date.today() + timedelta(days=30), key=prefix + "_next")
        note = st.text_area("備考", key=prefix + "_note")
        submitted = st.form_submit_button("登録", use_container_width=True)
        if submitted:
            if not clean_text(no) or not clean_text(name):
                st.warning("車両番号と車両名を入力してください。")
            else:
                ok, msg = add_forklift(no, name, next_date, note)
                st.success(msg) if ok else st.error(msg)
                if ok:
                    st.rerun()

init_db()
seed_data()


st.markdown('''
<style>
.block-container { padding-top: 1rem; max-width: 1100px; }
section[data-testid="stSidebar"] { display: none !important; }
div[data-testid="stSelectbox"] { max-width: 520px; }
@media (max-width: 768px) {
  .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
  div[data-testid="stSelectbox"] { max-width: 100%; }
}
</style>
''', unsafe_allow_html=True)

st.title("🚜 野田組 フォークリフト始業前点検")
st.caption("フォークリフト専用 / QR管理 / 3年保存 / 管理者承認")

query_forklift = query_value("forklift")
query_admin = query_value("admin") == "true"

menu_options = ["点検入力", "管理者メニュー", "エラー検知", "異常一覧", "履歴・出力", "ログ整理", "フォークリフトマスター", "点検者マスター", "QRコード発行", "QR印刷台紙"]
default_menu = "管理者メニュー" if query_admin else "点検入力"
st.markdown("### メニュー")
menu = st.selectbox("メニューを選択", menu_options, index=menu_options.index(default_menu))

if menu == "点検入力":
    st.markdown("## 点検入力")
    forklifts = get_forklifts(True)
    if forklifts.empty:
        st.warning("登録フォークリフトはありません。")
        quick_register("input_empty")
        st.stop()

    options = forklifts["forklift_no"].tolist()
    if query_forklift and query_forklift in options:
        selected_no = query_forklift
        st.info(f"QR固定：{selected_no}")
    else:
        selected_no = st.selectbox("車両", options, format_func=lambda no: f"{no} / {forklifts.loc[forklifts['forklift_no'] == no, 'forklift_name'].iloc[0]}")
    forklift = get_forklift(selected_no)
    if forklift is None:
        st.error("車両が見つかりません。")
        st.stop()

    c1, c2 = st.columns(2)
    c1.metric("車両番号", forklift["forklift_no"])
    c2.metric("車両名", forklift["forklift_name"])

    today_done = get_today_inspection(selected_no)
    if today_done is not None and query_forklift:
        st.success("本日の点検は完了しています。")
        st.write(f"点検者：{today_done['inspector']}")
        st.write(f"保存日時：{today_done['inspected_at']}")
        st.success(f"判定：{today_done['result']}")
        with st.expander("点検内容"):
            st.table(get_items(today_done["id"]).rename(columns={"category": "分類", "item_name": "点検項目", "status": "判定"}))
            render_photos(today_done)
        if not st.checkbox("再点検として新しく記録する"):
            st.stop()

    inspection_date = st.date_input("点検日", value=date.today())
    st.caption(f"点検日：{ja_date(inspection_date)}")

    if forklift.get("use_locked", 0):
        st.error("このフォークリフトは使用禁止中です。")

    inspectors = get_inspectors(True)
    if inspectors.empty:
        inspector = st.text_input("点検者名")
    else:
        inspector = st.selectbox("点検者", inspectors["inspector_name"].tolist())
    meter = st.text_input("アワーメーター", placeholder="例：1234h")

    statuses = {}
    st.markdown("### 点検項目")
    for category, items in CHECK_ITEMS.items():
        st.markdown(f"#### {category}")
        for item in items:
            with st.container(border=True):
                st.write(f"**{item}**")
                statuses[item] = st.radio("判定", ["良好", "要整備（使用可）", "異常あり", "対象外"], horizontal=True, key=f"{selected_no}_{category}_{item}")

    has_abnormal = any(v == "異常あり" for v in statuses.values())
    abnormal_detail = ""
    action_detail = ""
    photos = []
    if has_abnormal:
        st.error("異常あり：使用不可として保存されます。")
        abnormal_detail = st.text_area("異常内容 ※必須")
        action_detail = st.text_area("対応内容 ※必須")
        photos = st.file_uploader("写真添付 ※必須・最大4枚", type=["jpg", "jpeg", "png", "webp", "heic"], accept_multiple_files=True)
        if photos and len(photos) > 4:
            photos = photos[:4]
    st.error("最終判定：使用不可") if has_abnormal else st.success("最終判定：使用可")

    if st.button("点検記録を保存", type="primary", use_container_width=True):
        if not clean_text(inspector):
            st.warning("点検者名を入力してください。")
        elif has_abnormal and (not clean_text(abnormal_detail) or not clean_text(action_detail) or not photos):
            st.warning("異常ありの場合は異常内容・対応内容・写真が必須です。")
        else:
            save_inspection(forklift, inspection_date, inspector, meter, statuses, abnormal_detail, action_detail, photos)
            st.success("保存しました。")
            st.balloons()

elif menu == "管理者メニュー":
    st.markdown("## 管理者メニュー")
    if require_admin():
        errors, warnings = system_checks()
        unchecked = today_unchecked()
        abnormal = get_inspections("result=?", ("使用不可",))
        unconfirmed = abnormal[abnormal["manager_confirmed"] == 0] if not abnormal.empty else pd.DataFrame()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("本日未点検", len(unchecked))
        c2.metric("異常件数", len(abnormal))
        c3.metric("未承認異常", len(unconfirmed))
        c4.metric("登録車両", len(get_forklifts(False)))
        for e in errors:
            st.error(e)
        for w in warnings:
            st.warning(w)
        st.markdown("### 本日未点検")
        if unchecked.empty:
            st.success("本日の未点検はありません。")
        else:
            for _, r in unchecked.iterrows():
                st.error(f"{r['forklift_no']} / {r['forklift_name']}")
        st.markdown("### 管理者QR")
        st.image(make_qr_png(admin_url()), caption=admin_url(), width=260)

elif menu == "エラー検知":
    st.markdown("## エラー検知")
    if require_admin():
        errors, warnings = system_checks()
        if not errors and not warnings:
            st.success("エラーはありません。")
        for e in errors:
            st.error(e)
        for w in warnings:
            st.warning(w)

elif menu == "異常一覧":
    st.markdown("## 異常一覧")
    if require_admin():
        df = get_inspections("result=?", ("使用不可",))
        manager_name = st.text_input("管理者名")
        if df.empty:
            st.info("異常記録はありません。")
        else:
            for _, row in df.iterrows():
                with st.container(border=True):
                    st.markdown(f"### {row['forklift_no']} / {row['forklift_name']}")
                    st.error("使用不可")
                    st.write(f"点検日：{row['inspection_date']}")
                    st.write(f"点検者：{row['inspector']}")
                    st.write(f"異常内容：{clean_text(row['abnormal_detail'])}")
                    st.write(f"対応内容：{clean_text(row['action_detail'])}")
                    render_photos(row)
                    st.table(get_items(row["id"]).rename(columns={"category": "分類", "item_name": "点検項目", "status": "判定"}))
                    if row["manager_confirmed"]:
                        st.success(f"確認済：{row['manager_name']} / {row['manager_confirmed_at']}")
                    else:
                        if st.button("管理者確認して使用禁止解除", key=f"confirm_{row['id']}"):
                            if not clean_text(manager_name):
                                st.warning("管理者名を入力してください。")
                            else:
                                confirm_inspection(row["id"], row["forklift_no"], manager_name)
                                st.success("確認しました。")
                                st.rerun()

elif menu == "履歴・出力":
    st.markdown("## 履歴・出力")
    if require_admin():
        c1, c2, c3 = st.columns(3)
        start = c1.date_input("開始日", value=date.today().replace(day=1))
        end = c2.date_input("終了日", value=date.today())
        result_filter = c3.selectbox("判定", ["すべて", "使用可", "使用不可"])
        where = "inspection_date BETWEEN ? AND ?"
        params = [start.isoformat(), end.isoformat()]
        if result_filter != "すべて":
            where += " AND result=?"
            params.append(result_filter)
        df = get_inspections(where, tuple(params))
        st.metric("件数", len(df))
        if df.empty:
            st.info("該当記録はありません。")
        else:
            st.dataframe(make_export_df(df), use_container_width=True)
            export = make_export_df(df)
            st.download_button("Excel出力", data=excel_bytes(export), file_name="フォークリフト点検.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            st.download_button("CSV出力", data=csv_bytes(export), file_name="フォークリフト点検.csv", mime="text/csv", use_container_width=True)

elif menu == "ログ整理":
    st.markdown("## ログ整理")
    if require_admin():
        st.warning("削除前にExcel/CSV出力してください。")
        c1, c2 = st.columns(2)
        start = c1.date_input("削除開始日", value=date.today() - timedelta(days=RETENTION_DAYS))
        end = c2.date_input("削除終了日", value=date.today() - timedelta(days=RETENTION_DAYS + 1))
        df = get_inspections("inspection_date BETWEEN ? AND ?", (start.isoformat(), end.isoformat()))
        st.metric("削除対象", len(df))
        code = st.text_input("管理者コード", type="password")
        if st.button("この期間のログを削除", type="primary", use_container_width=True):
            if code != ADMIN_CODE:
                st.error("管理者コードが違います。")
            else:
                count = delete_logs(start, end)
                st.success(f"{count}件削除しました。")
                st.rerun()

elif menu == "フォークリフトマスター":
    st.markdown("## フォークリフトマスター")
    if require_admin():
        with st.form("add_forklift_form"):
            st.markdown("### 追加")
            no = st.text_input("車両番号", placeholder="FL-003")
            name = st.text_input("車両名", placeholder="フォークリフト3号")
            next_date = st.date_input("次回点検日", value=date.today() + timedelta(days=30))
            note = st.text_area("備考")
            if st.form_submit_button("登録", use_container_width=True):
                if not clean_text(no) or not clean_text(name):
                    st.warning("車両番号と車両名を入力してください。")
                else:
                    ok, msg = add_forklift(no, name, next_date, note)
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        st.rerun()

        df = get_forklifts(False)
        st.markdown("### 登録フォークリフト")
        if df.empty:
            st.info("登録フォークリフトはありません。")
            quick_register("master_empty")
        else:
            with st.expander("フォークリフトを選んで削除する"):
                target = st.selectbox("削除する号車", df["forklift_no"].tolist(), format_func=lambda x: f"{x} / {df.loc[df['forklift_no'] == x, 'forklift_name'].iloc[0]}")
                code = st.text_input("削除用 管理者コード", type="password")
                if st.button("選択した号車を削除", type="primary", use_container_width=True):
                    if code != ADMIN_CODE:
                        st.error("管理者コードが違います。")
                    else:
                        count = delete_forklift(target)
                        if count > 0:
                            st.success(f"{target} を削除しました。")
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
                    with st.expander("この号車を削除"):
                        code_each = st.text_input("管理者コード", type="password", key=f"del_code_{row['forklift_no']}")
                        if st.button("削除実行", key=f"del_btn_{row['forklift_no']}", use_container_width=True):
                            if code_each != ADMIN_CODE:
                                st.error("管理者コードが違います。")
                            else:
                                target_each = row["forklift_no"]
                                count = delete_forklift(target_each)
                                if count > 0:
                                    st.success(f"{target_each} を削除しました。")
                                else:
                                    st.warning("削除対象が見つかりませんでした。")
                                st.rerun()

            st.markdown("### 編集")
            edit = st.selectbox("編集する号車", df["forklift_no"].tolist(), key="edit_select")
            row = df[df["forklift_no"] == edit].iloc[0]
            new_name = st.text_input("車両名", value=row["forklift_name"])
            old_next = parse_date(row.get("next_inspection_date"))
            new_next = st.date_input("次回点検日", value=old_next or date.today())
            new_note = st.text_area("備考", value=clean_text(row.get("note")))
            active = st.radio("状態", ["有効", "無効"], index=0 if row["active"] else 1, horizontal=True)
            c1, c2 = st.columns(2)
            if c1.button("更新", use_container_width=True):
                update_forklift(edit, new_name, active == "有効", new_next, new_note)
                st.success("更新しました。")
                st.rerun()
            if c2.button("使用禁止を解除", use_container_width=True):
                reset_forklift_lock(edit)
                st.success("解除しました。")
                st.rerun()

elif menu == "点検者マスター":
    st.markdown("## 点検者マスター")
    if require_admin():
        with st.form("add_inspector_form"):
            st.markdown("### 追加")
            name = st.text_input("点検者名")
            note = st.text_area("備考")
            certs = st.file_uploader("資格者証 最大4枚", type=["jpg", "jpeg", "png", "webp", "heic"], accept_multiple_files=True)
            if st.form_submit_button("登録", use_container_width=True):
                if not clean_text(name):
                    st.warning("点検者名を入力してください。")
                else:
                    if certs and len(certs) > 4:
                        certs = certs[:4]
                    ok, msg = add_inspector(name, note, certs)
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        st.rerun()

        df = get_inspectors(False)
        if df.empty:
            st.info("点検者は未登録です。")
        else:
            for _, row in df.iterrows():
                with st.container(border=True):
                    st.write(f"**点検者名**\n{row['inspector_name']}")
                    st.write(f"状態：{'有効' if row['active'] else '無効'}")
                    if clean_text(row.get("note")):
                        st.write(f"備考：{clean_text(row['note'])}")
                    render_certs(row)
                    if st.button("この点検者を削除", key=f"ins_del_{row['id']}"):
                        delete_inspector(row["id"])
                        st.success("削除しました。")
                        st.rerun()

elif menu == "QRコード発行":
    st.markdown("## QRコード発行")
    if require_admin():
        df = get_forklifts(True)
        if df.empty:
            st.warning("登録フォークリフトはありません。")
            quick_register("qr_empty")
        else:
            selected = st.selectbox("QRを作る号車", df["forklift_no"].tolist(), format_func=lambda x: f"{x} / {df.loc[df['forklift_no'] == x, 'forklift_name'].iloc[0]}")
            url = qr_url(selected)
            img = make_qr_png(url)
            st.code(url)
            st.image(img, width=280)
            st.download_button("QRダウンロード", data=img, file_name=f"{selected}_QR.png", mime="image/png", use_container_width=True)
            st.markdown("### 管理者QR")
            admin_img = make_qr_png(admin_url())
            st.image(admin_img, width=280)
            st.download_button("管理者QRダウンロード", data=admin_img, file_name="管理者QR.png", mime="image/png", use_container_width=True)

elif menu == "QR印刷台紙":
    st.markdown("## QR印刷台紙")
    if require_admin():
        df = get_forklifts(True)
        if df.empty:
            st.warning("登録フォークリフトはありません。")
            quick_register("qr_print_empty")
            st.stop()
        cols = st.columns(3)
        for i, (_, row) in enumerate(df.iterrows()):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"### {row['forklift_no']}")
                    st.write(row["forklift_name"])
                    st.image(make_qr_png(qr_url(row["forklift_no"])), width=220)
        st.markdown("### 管理者QR")
        st.image(make_qr_png(admin_url()), width=260)
