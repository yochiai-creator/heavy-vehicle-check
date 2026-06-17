import sqlite3
from datetime import datetime, date, timedelta
from io import BytesIO
import urllib.parse

import pandas as pd
import qrcode
import streamlit as st

st.set_page_config(page_title="野田組 フォークリフト始業前点検", page_icon="🚜", layout="wide")

APP_URL = "https://heavy-vehicle-check-ghka28mxhavp4qrjpnkb7b.streamlit.app"
ADMIN_CODE = "1224"
DB_PATH = "forklift_check.db"
RETENTION_DAYS = 1095
WEEK_JA = ["月", "火", "水", "木", "金", "土", "日"]

CHECK_ITEMS = {
    "走行装置": ["ブレーキ", "駐車ブレーキ", "ハンドル・操舵装置", "タイヤ・ホイール"],
    "荷役装置": ["フォーク損傷", "フォーク固定ピン", "バックレスト", "マスト損傷", "リフトチェーン張り", "リフトチェーン給油状態", "荷重計（装備車のみ）"],
    "油圧装置": ["リフトシリンダー損傷", "チルトシリンダー損傷", "油圧ホース", "油漏れ"],
    "安全装置": ["ヘッドガード", "シートベルト", "ライト", "バックブザー", "ホーン", "ミラー"],
    "エンジン・電源": ["バッテリー", "燃料", "エンジンオイル", "冷却水"],
    "外観": ["車体損傷", "ボルト・ナット緩み", "異物付着"],
}

def ja_date(d):
    return "" if not d else f"{d.year}年{d.month}月{d.day}日（{WEEK_JA[d.weekday()]}）"

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

def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    con = connect(); cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS forklifts (
        forklift_no TEXT PRIMARY KEY,
        forklift_name TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        use_locked INTEGER DEFAULT 0,
        next_inspection_date TEXT,
        note TEXT,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS inspectors (
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
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS inspections (
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
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS inspection_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inspection_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        item_name TEXT NOT NULL,
        status TEXT NOT NULL
    )""")
    con.commit(); con.close()

def seed_data():
    con = connect(); cur = con.cursor(); cur.execute("SELECT COUNT(*) FROM forklifts")
    if cur.fetchone()[0] == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        nd = (date.today() + timedelta(days=30)).isoformat()
        for no, name in [("FL-001", "フォークリフト1号"), ("FL-002", "フォークリフト2号")]:
            cur.execute("INSERT INTO forklifts VALUES (?, ?, 1, 0, ?, '', ?)", (no, name, nd, now))
    con.commit(); con.close()

def get_forklifts(active_only=True):
    con = connect()
    sql = "SELECT * FROM forklifts" + (" WHERE active=1" if active_only else "") + " ORDER BY forklift_no"
    df = pd.read_sql_query(sql, con); con.close()
    for c in ["forklift_no", "forklift_name", "note"]:
        if c in df.columns:
            df[c] = df[c].apply(clean_text)
    return df

def get_forklift(no):
    con = connect(); df = pd.read_sql_query("SELECT * FROM forklifts WHERE forklift_no=?", con, params=(clean_text(no),)); con.close()
    return None if df.empty else df.iloc[0].to_dict()

def add_forklift(no, name, next_d, note):
    con = connect()
    try:
        con.execute("INSERT INTO forklifts VALUES (?, ?, 1, 0, ?, ?, ?)", (clean_text(no), clean_text(name), next_d.isoformat(), clean_text(note), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        con.commit(); return True, "フォークリフトを登録しました。"
    except sqlite3.IntegrityError:
        return False, "同じ車両番号が既にあります。"
    finally:
        con.close()

def update_forklift(no, name, active, next_d, note):
    con = connect(); con.execute("UPDATE forklifts SET forklift_name=?, active=?, next_inspection_date=?, note=? WHERE forklift_no=?", (clean_text(name), 1 if active else 0, next_d.isoformat(), clean_text(note), clean_text(no))); con.commit(); con.close()

def delete_forklift(no):
    con = connect(); cur = con.cursor(); cur.execute("DELETE FROM forklifts WHERE forklift_no=?", (clean_text(no),)); n = cur.rowcount; con.commit(); con.close(); return n

def reset_forklift_lock(no):
    con = connect(); con.execute("UPDATE forklifts SET use_locked=0 WHERE forklift_no=?", (clean_text(no),)); con.commit(); con.close()

def get_inspectors(active_only=True):
    con = connect(); sql = "SELECT * FROM inspectors" + (" WHERE active=1" if active_only else "") + " ORDER BY inspector_name"
    df = pd.read_sql_query(sql, con); con.close()
    if not df.empty:
        df["inspector_name"] = df["inspector_name"].apply(clean_text)
    return df

def add_inspector(name, note, certs):
    data = []
    for c in (certs or [])[:4]:
        data.append((c.name, c.getvalue()))
    while len(data) < 4:
        data.append(("", None))
    con = connect()
    try:
        con.execute("""INSERT INTO inspectors(inspector_name,active,note,cert1_name,cert1_bytes,cert2_name,cert2_bytes,cert3_name,cert3_bytes,cert4_name,cert4_bytes,created_at)
            VALUES (?,1,?,?,?,?,?,?,?,?,?,?)""", (clean_text(name), clean_text(note), data[0][0], data[0][1], data[1][0], data[1][1], data[2][0], data[2][1], data[3][0], data[3][1], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        con.commit(); return True, "点検者を登録しました。"
    except sqlite3.IntegrityError:
        return False, "同じ点検者名が既にあります。"
    finally:
        con.close()

def update_inspector(i, name, active, note, certs, replace):
    con = connect()
    if replace:
        data = []
        for c in (certs or [])[:4]: data.append((c.name, c.getvalue()))
        while len(data) < 4: data.append(("", None))
        con.execute("""UPDATE inspectors SET inspector_name=?, active=?, note=?, cert1_name=?, cert1_bytes=?, cert2_name=?, cert2_bytes=?, cert3_name=?, cert3_bytes=?, cert4_name=?, cert4_bytes=? WHERE id=?""", (clean_text(name), 1 if active else 0, clean_text(note), data[0][0], data[0][1], data[1][0], data[1][1], data[2][0], data[2][1], data[3][0], data[3][1], i))
    else:
        con.execute("UPDATE inspectors SET inspector_name=?, active=?, note=? WHERE id=?", (clean_text(name), 1 if active else 0, clean_text(note), i))
    con.commit(); con.close()

def delete_inspector(i):
    con = connect(); con.execute("DELETE FROM inspectors WHERE id=?", (i,)); con.commit(); con.close()

def save_inspection(forklift, inspection_date, inspector, meter, statuses, abnormal_detail, action_detail, photos):
    abnormal = any(v == "異常あり" for v in statuses.values())
    result = "使用不可" if abnormal else "使用可"
    data = []
    for p in (photos or [])[:4]: data.append((p.name, p.getvalue()))
    while len(data) < 4: data.append(("", None))
    con = connect(); cur = con.cursor()
    cur.execute("""INSERT INTO inspections(inspected_at,inspection_date,forklift_no,forklift_name,inspector,meter,result,abnormal_detail,action_detail,photo1_name,photo1_bytes,photo2_name,photo2_bytes,photo3_name,photo3_bytes,photo4_name,photo4_bytes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inspection_date.isoformat(), forklift["forklift_no"], forklift["forklift_name"], clean_text(inspector), clean_text(meter), result, clean_text(abnormal_detail), clean_text(action_detail), data[0][0], data[0][1], data[1][0], data[1][1], data[2][0], data[2][1], data[3][0], data[3][1]))
    iid = cur.lastrowid
    for cat, items in CHECK_ITEMS.items():
        for item in items:
            cur.execute("INSERT INTO inspection_items(inspection_id,category,item_name,status) VALUES (?,?,?,?)", (iid, cat, item, statuses.get(item, "対象外")))
    if abnormal:
        cur.execute("UPDATE forklifts SET use_locked=1 WHERE forklift_no=?", (forklift["forklift_no"],))
    con.commit(); con.close()

def get_inspections(where="", params=()):
    con = connect(); sql = "SELECT * FROM inspections" + (" WHERE " + where if where else "") + " ORDER BY inspection_date DESC, inspected_at DESC"
    df = pd.read_sql_query(sql, con, params=params); con.close(); return df

def get_items(iid):
    con = connect(); df = pd.read_sql_query("SELECT category,item_name,status FROM inspection_items WHERE inspection_id=?", con, params=(iid,)); con.close(); return df

def get_today_inspection(no):
    df = get_inspections("forklift_no=? AND inspection_date=?", (no, date.today().isoformat()))
    return None if df.empty else df.iloc[0]

def confirm_inspection(iid, no, manager):
    con = connect(); con.execute("UPDATE inspections SET manager_confirmed=1, manager_name=?, manager_confirmed_at=? WHERE id=?", (clean_text(manager), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), iid)); con.execute("UPDATE forklifts SET use_locked=0 WHERE forklift_no=?", (no,)); con.commit(); con.close()

def update_inspection_date(iid, d):
    con = connect(); con.execute("UPDATE inspections SET inspection_date=? WHERE id=?", (d.isoformat(), iid)); con.commit(); con.close()

def delete_logs(s, e):
    con = connect(); cur = con.cursor(); cur.execute("SELECT id FROM inspections WHERE inspection_date BETWEEN ? AND ?", (s.isoformat(), e.isoformat())); ids = [r[0] for r in cur.fetchall()]
    if ids:
        ph = ','.join(['?'] * len(ids)); cur.execute(f"DELETE FROM inspection_items WHERE inspection_id IN ({ph})", ids); cur.execute(f"DELETE FROM inspections WHERE id IN ({ph})", ids)
    con.commit(); con.close(); return len(ids)

def qr_png(url):
    img = qrcode.make(url); buf = BytesIO(); img.save(buf, format='PNG'); return buf.getvalue()

def qr_url(no): return APP_URL.rstrip() + "/?forklift=" + urllib.parse.quote(str(no), safe="")
def admin_url(): return APP_URL.rstrip() + "/?admin=true"

def q(key):
    try: v = st.query_params.get(key, "")
    except Exception: return ""
    if isinstance(v, list): v = v[0] if v else ""
    return urllib.parse.unquote(str(v or ""))

def parse_date(v):
    try: return datetime.strptime(v, "%Y-%m-%d").date() if v else None
    except Exception: return None

def render_imgs(row, prefix="photo", width=150):
    pairs = [(f"{prefix}{i}_name", f"{prefix}{i}_bytes") for i in range(1,5)] if prefix == "photo" else [(f"cert{i}_name", f"cert{i}_bytes") for i in range(1,5)]
    cols = st.columns(4); shown = False
    for idx, (n, b) in enumerate(pairs):
        if b in row.index and row[b] is not None:
            with cols[idx]: st.image(row[b], caption=row.get(n, ""), width=width)
            shown = True
    if not shown: st.caption("添付なし")

def unchecked_today():
    fl = get_forklifts(True); checked = get_inspections("inspection_date=?", (date.today().isoformat(),)); s = set(checked["forklift_no"].tolist()) if not checked.empty else set()
    return fl[~fl["forklift_no"].isin(s)] if not fl.empty else pd.DataFrame()

def export_df(df):
    out = df.drop(columns=["photo1_bytes","photo2_bytes","photo3_bytes","photo4_bytes"], errors="ignore").copy()
    out = out.rename(columns={"id":"ID","inspected_at":"保存日時","inspection_date":"点検日","forklift_no":"車両番号","forklift_name":"車両名","inspector":"点検者","meter":"アワーメーター","result":"判定","abnormal_detail":"異常内容","action_detail":"対応内容","manager_confirmed":"管理者確認","manager_name":"管理者名","manager_confirmed_at":"管理者確認日時"})
    if "管理者確認" in out.columns: out["管理者確認"] = out["管理者確認"].apply(lambda x: "確認済" if x else "未確認")
    texts = []
    for _, r in df.iterrows():
        items = get_items(r["id"]); texts.append(" / ".join([f"{x['category']}:{x['item_name']}={x['status']}" for _, x in items.iterrows()]))
    out["点検項目"] = texts
    return out

def excel_bytes(df):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        wb = writer.book; title = wb.add_format({"bold":True,"font_size":18,"align":"center","fg_color":"#1F4E78","font_color":"white"}); head = wb.add_format({"bold":True,"font_color":"white","fg_color":"#305496","border":1}); cell = wb.add_format({"border":1,"text_wrap":True,"valign":"top"})
        cover = wb.add_worksheet("表紙"); cover.merge_range("A1:H2", "野田組 フォークリフト始業前点検記録", title); cover.write("A4", "出力日時"); cover.write("B4", datetime.now().strftime("%Y/%m/%d %H:%M")); cover.write("A5", "件数"); cover.write("B5", len(df))
        df.to_excel(writer, index=False, sheet_name="点検履歴", startrow=3); ws = writer.sheets["点検履歴"]
        if len(df.columns):
            ws.merge_range(0,0,1,len(df.columns)-1,"フォークリフト始業前点検 一覧", title)
            for c,n in enumerate(df.columns): ws.write(3,c,n,head); ws.set_column(c,c,60 if n=="点検項目" else 18)
            for r in range(len(df)):
                for c in range(len(df.columns)): ws.write(r+4,c,"" if pd.isna(df.iloc[r,c]) else df.iloc[r,c], cell)
            ws.freeze_panes(4,0); ws.autofilter(3,0,len(df)+3,len(df.columns)-1); ws.set_landscape(); ws.fit_to_pages(1,0)
    return buf.getvalue()

def require_admin():
    if st.session_state.get("admin_ok"): return True
    st.markdown("### 管理者認証"); code = st.text_input("管理者コード", type="password")
    if st.button("認証"):
        if code == ADMIN_CODE: st.session_state.admin_ok = True; st.rerun()
        else: st.error("管理者コードが違います。")
    return False

def quick_register(prefix):
    st.markdown("### フォークリフトを登録してください")
    with st.form(f"{prefix}_form"):
        no = st.text_input("車両番号", placeholder="例：FL-001"); name = st.text_input("車両名", placeholder="例：フォークリフト1号"); nd = st.date_input("次回点検日", value=date.today()+timedelta(days=30)); note = st.text_area("備考")
        if st.form_submit_button("登録", use_container_width=True):
            if not no or not name: st.warning("車両番号と車両名を入力してください。")
            else:
                ok,msg = add_forklift(no,name,nd,note); st.success(msg) if ok else st.error(msg)
                if ok: st.rerun()

init_db(); seed_data()

st.title("🚜 野田組 フォークリフト始業前点検")
st.caption("フォークリフト専用 / 労働安全衛生法対応 / QR管理 / 3年保存 / 管理者承認")
query_no = q("forklift"); query_admin = q("admin") == "true"; fl_now = get_forklifts(True); valid = set(fl_now["forklift_no"].tolist()) if not fl_now.empty else set()
if query_no and query_no not in valid: st.warning("QRコードの車両番号がマスターにありません。車両を選択してください。"); query_no = ""
if query_no: st.success(f"QRコードから車両を固定しました：{query_no}")
menu_options=["点検入力","管理者メニュー","エラー検知","異常一覧","履歴・出力","ログ整理","フォークリフトマスター","点検者マスター","QRコード発行","QR印刷台紙"]
menu = st.sidebar.radio("メニュー", menu_options, index=1 if query_admin else 0)

if menu == "点検入力":
    st.markdown("## 点検入力"); fl = get_forklifts(True)
    if fl.empty: st.warning("登録フォークリフトはありません。"); quick_register("empty_inspection"); st.stop()
    opts = fl["forklift_no"].tolist()
    if query_no and query_no in opts: selected = query_no; st.info(f"車両固定：{selected} / {fl.loc[fl['forklift_no']==selected,'forklift_name'].iloc[0]}")
    else: selected = st.selectbox("車両", opts, format_func=lambda x:f"{x} / {fl.loc[fl['forklift_no']==x,'forklift_name'].iloc[0]}")
    forklift = get_forklift(selected); c1,c2 = st.columns(2); c1.metric("車両番号", forklift["forklift_no"]); c2.metric("車両名", forklift["forklift_name"])
    done = get_today_inspection(selected)
    if done is not None and query_no:
        st.success("本日の日常点検は完了しています。"); st.write(f"点検者：{done['inspector']}"); st.write(f"保存日時：{done['inspected_at']}"); st.success(f"判定：{done['result']}") if done['result']=="使用可" else st.error(f"判定：{done['result']}")
        with st.expander("本日の点検内容を確認"): st.table(get_items(done["id"]).rename(columns={"category":"分類","item_name":"点検項目","status":"判定"})); render_imgs(done)
        if not st.checkbox("再点検として新しく記録する"): st.stop()
    elif done is not None: st.info("この車両は本日すでに点検済みです。必要なら再点検として保存できます。")
    inspection_date = st.date_input("点検日", value=date.today()); st.caption(f"点検日：{ja_date(inspection_date)}")
    if forklift.get("use_locked",0): st.error("このフォークリフトは使用禁止中です。管理者確認まで使用しないでください。")
    ins = get_inspectors(True); inspector = st.text_input("点検者名") if ins.empty else st.selectbox("点検者", ins["inspector_name"].tolist())
    meter = st.text_input("アワーメーター", placeholder="例：1234h")
    st.markdown("### 点検項目"); st.caption("判定：良好 / 要整備（使用可） / 異常あり / 対象外。異常ありは使用停止・写真添付必須です。")
    statuses = {}
    for cat,items in CHECK_ITEMS.items():
        st.markdown(f"#### {cat}")
        for item in items:
            with st.container(border=True): st.markdown(f"**{item}**"); statuses[item] = st.radio("判定", ["良好","要整備（使用可）","異常あり","対象外"], horizontal=True, key=f"{selected}_{cat}_{item}")
    abnormal = any(v=="異常あり" for v in statuses.values()); detail=""; action=""; photos=[]
    if abnormal:
        st.error("異常あり：使用不可として保存されます。"); detail = st.text_area("異常内容 ※必須"); action = st.text_area("対応内容 ※必須"); photos = st.file_uploader("写真添付 ※必須・最大4枚", type=["jpg","jpeg","png","webp","heic"], accept_multiple_files=True); photos = (photos or [])[:4]
    if abnormal: st.error("最終判定：使用不可")
    else: st.success("最終判定：使用可")
    if st.button("点検記録を保存", type="primary", use_container_width=True):
        if not inspector: st.warning("点検者名を入力してください。")
        elif abnormal and (not detail or not action or not photos): st.warning("異常ありの場合は、異常内容・対応内容・写真添付が必須です。")
        else: save_inspection(forklift, inspection_date, inspector, meter, statuses, detail, action, photos); st.success("点検記録を保存しました。"); st.balloons()

elif menu == "管理者メニュー":
    st.markdown("## 管理者メニュー")
    if require_admin():
        unchecked=unchecked_today(); abnormal=get_inspections("result=?", ("使用不可",)); unconf=abnormal[abnormal["manager_confirmed"]==0] if not abnormal.empty else pd.DataFrame()
        c1,c2,c3,c4=st.columns(4); c1.metric("本日未点検",len(unchecked)); c2.metric("異常件数",len(abnormal)); c3.metric("未承認異常",len(unconf)); c4.metric("登録車両",len(get_forklifts(False)))
        if get_forklifts(True).empty: st.warning("登録フォークリフトがありません。"); quick_register("admin_empty")
        st.markdown("### 本日未点検一覧")
        if unchecked.empty: st.success("本日の未点検フォークリフトはありません。")
        else:
            for _,r in unchecked.iterrows(): st.error(f"{r['forklift_no']} / {r['forklift_name']}")
        png=qr_png(admin_url()); st.markdown("### 管理者QR"); st.image(png,width=260); st.download_button("管理者QRダウンロード", data=png, file_name="管理者QR.png", mime="image/png")

elif menu == "エラー検知":
    st.markdown("## エラー検知")
    if require_admin():
        errs=[]; warns=[]
        if get_forklifts(True).empty: errs.append("フォークリフトが登録されていません。")
        if get_inspectors(True).empty: warns.append("点検者が登録されていません。")
        locked=get_forklifts(True); locked=locked[locked["use_locked"]==1] if not locked.empty else pd.DataFrame()
        if not locked.empty: errs.append(f"使用禁止中が{len(locked)}台あります。")
        if not errs and not warns: st.success("エラーは検知されていません。")
        for e in errs: st.error(e)
        for w in warns: st.warning(w)

elif menu == "異常一覧":
    st.markdown("## 異常一覧")
    if require_admin():
        df=get_inspections("result=?", ("使用不可",)); manager=st.text_input("管理者名")
        if df.empty: st.info("異常記録はありません。")
        else:
            for _,row in df.iterrows():
                with st.container(border=True):
                    st.markdown(f"### {row['forklift_no']} / {row['forklift_name']}"); st.write(f"点検日：{ja_date(parse_date(row['inspection_date']))}"); st.write(f"点検者：{row['inspector']}"); st.error("使用不可"); st.write(f"異常内容：{row['abnormal_detail']}"); st.write(f"対応内容：{row['action_detail']}"); render_imgs(row); st.table(get_items(row["id"]).rename(columns={"category":"分類","item_name":"点検項目","status":"判定"}))
                    if row["manager_confirmed"]: st.success(f"管理者確認済：{row['manager_name']} / {row['manager_confirmed_at']}")
                    elif st.button("管理者確認して使用禁止解除", key=f"confirm_{row['id']}"):
                        if not manager: st.warning("管理者名を入力してください。")
                        else: confirm_inspection(row["id"], row["forklift_no"], manager); st.rerun()

elif menu == "履歴・出力":
    st.markdown("## 履歴・出力")
    if require_admin():
        a,b,c=st.columns(3); start=a.date_input("開始日", value=date.today().replace(day=1)); end=b.date_input("終了日", value=date.today()); f=c.selectbox("判定", ["すべて","使用可","使用不可"])
        where="inspection_date BETWEEN ? AND ?"; params=[start.isoformat(), end.isoformat()]
        if f != "すべて": where += " AND result=?"; params.append(f)
        df=get_inspections(where, tuple(params)); st.metric("件数", len(df))
        if df.empty: st.info("該当する記録がありません。")
        else:
            for _,row in df.iterrows():
                with st.container(border=True):
                    c1,c2,c3,c4=st.columns(4); c1.write(f"**点検日**\n{ja_date(parse_date(row['inspection_date']))}"); c2.write(f"**車両**\n{row['forklift_no']} / {row['forklift_name']}"); c3.write(f"**点検者**\n{row['inspector']}")
                    if row["result"] == "使用不可": c4.error("使用不可")
                    else: c4.success("使用可")
                    render_imgs(row, width=140)
                    nd=st.date_input("点検日修正", value=parse_date(row["inspection_date"]) or date.today(), key=f"d_{row['id']}")
                    if st.button("この点検日を修正", key=f"u_{row['id']}"): update_inspection_date(row["id"], nd); st.rerun()
            out=export_df(df); st.download_button("Excel出力（表形式）", data=excel_bytes(out), file_name="野田組_フォークリフト始業前点検.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True); st.download_button("CSV出力", data=out.to_csv(index=False).encode("utf-8-sig"), file_name="野田組_フォークリフト始業前点検.csv", mime="text/csv", use_container_width=True)

elif menu == "ログ整理":
    st.markdown("## ログ整理")
    if require_admin():
        s=st.date_input("削除開始日", value=date.today()-timedelta(days=RETENTION_DAYS)); e=st.date_input("削除終了日", value=date.today()-timedelta(days=RETENTION_DAYS+1)); df=get_inspections("inspection_date BETWEEN ? AND ?", (s.isoformat(), e.isoformat())); st.metric("対象件数", len(df)); code=st.text_input("管理者コード", type="password")
        if st.button("この期間のログを削除", type="primary"):
            if code != ADMIN_CODE: st.error("管理者コードが違います。")
            else: st.success(f"{delete_logs(s,e)}件削除しました。"); st.rerun()

elif menu == "フォークリフトマスター":
    st.markdown("## フォークリフトマスター")
    if require_admin():
        quick_register("master_add")
        df=get_forklifts(False); st.markdown("### 登録フォークリフト")
        if df.empty: st.info("登録フォークリフトはありません。")
        else:
            with st.expander("フォークリフトを選んで削除する"):
                t=st.selectbox("削除するフォークリフト", df["forklift_no"].tolist(), format_func=lambda x:f"{x} / {df.loc[df['forklift_no']==x,'forklift_name'].iloc[0]}"); code=st.text_input("削除用 管理者コード", type="password")
                if st.button("選択したフォークリフトを削除", type="primary"):
                    if code != ADMIN_CODE: st.error("管理者コードが違います。")
                    else: delete_forklift(t); st.rerun()
            for _,r in df.iterrows():
                with st.container(border=True): st.write(f"**車両番号**\n{r['forklift_no']}"); st.write(f"**車両名**\n{r['forklift_name']}"); st.write("有効" if r["active"] else "無効")
            t=st.selectbox("編集するフォークリフト", df["forklift_no"].tolist(), key="edit"); row=df[df["forklift_no"]==t].iloc[0]; nn=st.text_input("車両名", value=row["forklift_name"]); nd=st.date_input("次回点検日", value=parse_date(row.get("next_inspection_date")) or date.today()); note=st.text_area("備考", value=row.get("note","") or ""); active=st.radio("状態", ["有効","無効"], index=0 if row["active"] else 1, horizontal=True)
            if st.button("情報を更新"): update_forklift(t, nn, active=="有効", nd, note); st.rerun()
            if st.button("使用禁止を手動解除"): reset_forklift_lock(t); st.rerun()

elif menu == "点検者マスター":
    st.markdown("## 点検者マスター")
    if require_admin():
        with st.form("ins_add"):
            name=st.text_input("点検者名"); note=st.text_area("備考"); certs=st.file_uploader("資格者証添付 最大4枚", type=["jpg","jpeg","png","webp","heic"], accept_multiple_files=True)
            if st.form_submit_button("登録"):
                if not name: st.warning("点検者名を入力してください。")
                else: ok,msg=add_inspector(name,note,(certs or [])[:4]); st.success(msg) if ok else st.error(msg)
        df=get_inspectors(False)
        for _,r in df.iterrows():
            with st.container(border=True): st.write(f"**点検者名**\n{r['inspector_name']}"); st.write("有効" if r["active"] else "無効"); render_imgs(r, prefix="cert")
        if not df.empty:
            tid=st.selectbox("編集する点検者", df["id"].tolist(), format_func=lambda x:df.loc[df['id']==x,'inspector_name'].iloc[0]); row=df[df["id"]==tid].iloc[0]; nm=st.text_input("点検者名", value=row["inspector_name"]); ac=st.radio("状態", ["有効","無効"], index=0 if row["active"] else 1, horizontal=True, key="ia"); nt=st.text_area("備考", value=row.get("note","") or ""); rep=st.checkbox("資格者証を差し替える"); nc=st.file_uploader("新しい資格者証 最大4枚", type=["jpg","jpeg","png","webp","heic"], accept_multiple_files=True) if rep else []
            if st.button("点検者情報を更新"): update_inspector(tid,nm,ac=="有効",nt,(nc or [])[:4],rep); st.rerun()
            if st.button("この点検者を削除"): delete_inspector(tid); st.rerun()

elif menu == "QRコード発行":
    st.markdown("## QRコード発行")
    if require_admin():
        df=get_forklifts(True)
        if df.empty: st.warning("登録フォークリフトはありません。"); quick_register("qr")
        else:
            no=st.selectbox("QRを作るフォークリフト", df["forklift_no"].tolist(), format_func=lambda x:f"{x} / {df.loc[df['forklift_no']==x,'forklift_name'].iloc[0]}"); url=qr_url(no); png=qr_png(url); st.code(url); st.image(png,width=280); st.download_button("フォークリフトQRダウンロード", data=png, file_name=f"{no}_QR.png", mime="image/png"); admin=qr_png(admin_url()); st.image(admin,width=260); st.download_button("管理者QRダウンロード", data=admin, file_name="管理者QR.png", mime="image/png")

elif menu == "QR印刷台紙":
    st.markdown("## QR印刷台紙")
    if require_admin():
        df=get_forklifts(True)
        if df.empty: st.warning("登録フォークリフトはありません。"); quick_register("print"); st.stop()
        cols=st.columns(3)
        for i,(_,r) in enumerate(df.iterrows()):
            with cols[i%3]:
                with st.container(border=True): st.markdown(f"### {r['forklift_no']}"); st.write(r["forklift_name"]); url=qr_url(r["forklift_no"]); st.image(qr_png(url), width=220); st.caption(url)
        st.divider(); st.markdown("### 管理者用QR"); st.image(qr_png(admin_url()), width=260); st.caption(admin_url())
