
import os
import sqlite3
import csv
from datetime import datetime
from io import StringIO
import qrcode
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, Response

APP_TITLE = "野田組 重機・車両 始業前点検"
DB_PATH = "vehicle_check.db"
UPLOAD_FOLDER = "static/uploads"
QR_FOLDER = "static/qr"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = "nodagumi_vehicle_check_secret"

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

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_no TEXT UNIQUE NOT NULL,
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
            photo_path TEXT,
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

def seed():
    con = db()
    count = con.execute("SELECT COUNT(*) AS c FROM vehicles").fetchone()["c"]
    if count == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        samples = [
            ("FL-001", "フォークリフト1号", "forklift"),
            ("FL-002", "フォークリフト2号", "forklift"),
            ("WL-001", "ホイールローダー1号", "wheel_loader"),
            ("DP-001", "ダンプ1号", "dump"),
            ("BH-001", "バックホウ1号", "backhoe"),
            ("LT-001", "軽トラ1号", "light_truck"),
        ]
        for no, name, typ in samples:
            con.execute(
                "INSERT INTO vehicles(vehicle_no, vehicle_name, vehicle_type, created_at) VALUES (?, ?, ?, ?)",
                (no, name, typ, now)
            )
    con.commit()
    con.close()

def get_vehicle(vehicle_no):
    con = db()
    row = con.execute("SELECT * FROM vehicles WHERE vehicle_no = ?", (vehicle_no,)).fetchone()
    con.close()
    return row

def save_upload(file, vehicle_no):
    if not file or not file.filename:
        return ""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".heic"]:
        ext = ".jpg"
    filename = f"{vehicle_no}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)
    return path.replace("\\", "/")

def generate_qr_files():
    con = db()
    vehicles = con.execute("SELECT * FROM vehicles WHERE active = 1 ORDER BY vehicle_no").fetchall()
    con.close()

    # 起動直後など外部URLが分からない場合は相対URLのQRを作る
    for v in vehicles:
        url = f"/check/{v['vehicle_no']}"
        filename = f"{v['vehicle_no']}.png"
        path = os.path.join(QR_FOLDER, filename)
        qrcode.make(url).save(path)

@app.before_request
def setup():
    init_db()
    seed()

@app.route("/")
def index():
    vehicle_no = request.args.get("vehicle", "")
    con = db()
    vehicles = con.execute("SELECT * FROM vehicles WHERE active = 1 ORDER BY vehicle_no").fetchall()
    selected = con.execute("SELECT * FROM vehicles WHERE vehicle_no = ?", (vehicle_no,)).fetchone() if vehicle_no else None
    con.close()
    return render_template("index.html", app_title=APP_TITLE, vehicles=vehicles, selected=selected, vehicle_types=VEHICLE_TYPES)

@app.route("/check/<vehicle_no>", methods=["GET", "POST"])
def check(vehicle_no):
    vehicle = get_vehicle(vehicle_no)
    if not vehicle:
        flash("車両が見つかりません。", "error")
        return redirect(url_for("index"))

    items = CHECK_ITEMS.get(vehicle["vehicle_type"], CHECK_ITEMS["other"])

    if request.method == "POST":
        inspector = request.form.get("inspector", "").strip()
        meter = request.form.get("meter", "").strip()

        statuses = {}
        has_abnormal = False
        for item in items:
            status = request.form.get(f"item_{item}", "良好")
            statuses[item] = status
            if status == "異常あり":
                has_abnormal = True

        abnormal_detail = request.form.get("abnormal_detail", "").strip()
        action_detail = request.form.get("action_detail", "").strip()
        photo = request.files.get("photo")

        if not inspector:
            flash("点検者名を入力してください。", "error")
            return redirect(url_for("check", vehicle_no=vehicle_no))

        if has_abnormal and (not abnormal_detail or not action_detail or not photo or not photo.filename):
            flash("異常ありの場合は、異常内容・対応内容・写真添付が必須です。", "error")
            return redirect(url_for("check", vehicle_no=vehicle_no))

        result = "使用不可" if has_abnormal else "使用可"
        photo_path = save_upload(photo, vehicle_no) if has_abnormal else ""

        now = datetime.now()
        con = db()
        cur = con.cursor()
        cur.execute("""
            INSERT INTO inspections(
                inspected_at, inspection_date, vehicle_no, vehicle_name, vehicle_type,
                inspector, meter, result, abnormal_detail, action_detail, photo_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
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
            photo_path
        ))
        inspection_id = cur.lastrowid

        for item, status in statuses.items():
            cur.execute(
                "INSERT INTO inspection_items(inspection_id, item_name, status) VALUES (?, ?, ?)",
                (inspection_id, item, status)
            )

        if has_abnormal:
            cur.execute("UPDATE vehicles SET use_locked = 1 WHERE vehicle_no = ?", (vehicle_no,))

        con.commit()
        con.close()

        flash("点検記録を保存しました。", "success")
        return redirect(url_for("complete", inspection_id=inspection_id))

    return render_template("check.html", app_title=APP_TITLE, vehicle=vehicle, items=items, vehicle_types=VEHICLE_TYPES)

@app.route("/complete/<int:inspection_id>")
def complete(inspection_id):
    con = db()
    inspection = con.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    con.close()
    return render_template("complete.html", app_title=APP_TITLE, inspection=inspection)

@app.route("/admin")
def admin():
    con = db()
    inspections = con.execute("SELECT * FROM inspections ORDER BY inspected_at DESC LIMIT 200").fetchall()
    abnormal = con.execute("SELECT * FROM inspections WHERE result = '使用不可' ORDER BY inspected_at DESC").fetchall()
    vehicles = con.execute("SELECT * FROM vehicles ORDER BY vehicle_no").fetchall()
    con.close()
    return render_template(
        "admin.html",
        app_title=APP_TITLE,
        inspections=inspections,
        abnormal=abnormal,
        vehicles=vehicles
    )

@app.route("/confirm/<int:inspection_id>", methods=["POST"])
def confirm(inspection_id):
    manager_name = request.form.get("manager_name", "").strip()
    vehicle_no = request.form.get("vehicle_no", "").strip()

    if not manager_name:
        flash("管理者名を入力してください。", "error")
        return redirect(url_for("admin"))

    con = db()
    con.execute("""
        UPDATE inspections
        SET manager_confirmed = 1,
            manager_name = ?,
            manager_confirmed_at = ?
        WHERE id = ?
    """, (manager_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inspection_id))

    if vehicle_no:
        con.execute("UPDATE vehicles SET use_locked = 0 WHERE vehicle_no = ?", (vehicle_no,))

    con.commit()
    con.close()

    flash("管理者確認を完了し、使用禁止を解除しました。", "success")
    return redirect(url_for("admin"))

@app.route("/vehicles", methods=["GET", "POST"])
def vehicles():
    con = db()

    if request.method == "POST":
        vehicle_no = request.form.get("vehicle_no", "").strip()
        vehicle_name = request.form.get("vehicle_name", "").strip()
        vehicle_type = request.form.get("vehicle_type", "other")

        if not vehicle_no or not vehicle_name:
            flash("車両番号と車両名を入力してください。", "error")
        else:
            try:
                con.execute("""
                    INSERT INTO vehicles(vehicle_no, vehicle_name, vehicle_type, created_at)
                    VALUES (?, ?, ?, ?)
                """, (vehicle_no, vehicle_name, vehicle_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
                flash("車両を登録しました。", "success")
            except sqlite3.IntegrityError:
                flash("同じ車両番号が既にあります。", "error")

    rows = con.execute("SELECT * FROM vehicles ORDER BY vehicle_no").fetchall()
    con.close()
    return render_template("vehicles.html", app_title=APP_TITLE, vehicles=rows, vehicle_types=VEHICLE_TYPES)

@app.route("/vehicle_toggle/<vehicle_no>")
def vehicle_toggle(vehicle_no):
    con = db()
    row = con.execute("SELECT active FROM vehicles WHERE vehicle_no = ?", (vehicle_no,)).fetchone()
    if row:
        new_active = 0 if row["active"] else 1
        con.execute("UPDATE vehicles SET active = ? WHERE vehicle_no = ?", (new_active, vehicle_no))
        con.commit()
    con.close()
    return redirect(url_for("vehicles"))

@app.route("/qr")
def qr():
    base_url = request.url_root.rstrip("/")
    con = db()
    vehicles = con.execute("SELECT * FROM vehicles WHERE active = 1 ORDER BY vehicle_no").fetchall()
    con.close()

    qr_rows = []
    for v in vehicles:
        url = f"{base_url}/check/{v['vehicle_no']}"
        filename = f"{v['vehicle_no']}.png"
        path = os.path.join(QR_FOLDER, filename)
        qrcode.make(url).save(path)
        qr_rows.append({
            "vehicle": v,
            "url": url,
            "qr_path": "/" + path.replace("\\", "/")
        })

    return render_template("qr.html", app_title=APP_TITLE, qr_rows=qr_rows)

@app.route("/csv")
def export_csv():
    con = db()
    rows = con.execute("SELECT * FROM inspections ORDER BY inspected_at DESC").fetchall()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "日時", "点検日", "車両番号", "車両名", "車種", "点検者", "メーター",
        "判定", "異常内容", "対応内容", "写真", "管理者確認", "管理者名", "管理者確認日時", "点検項目"
    ])

    for r in rows:
        items = con.execute("SELECT item_name, status FROM inspection_items WHERE inspection_id = ?", (r["id"],)).fetchall()
        item_text = " / ".join([f"{i['item_name']}:{i['status']}" for i in items])
        writer.writerow([
            r["id"],
            r["inspected_at"],
            r["inspection_date"],
            r["vehicle_no"],
            r["vehicle_name"],
            VEHICLE_TYPES.get(r["vehicle_type"], r["vehicle_type"]),
            r["inspector"],
            r["meter"],
            r["result"],
            r["abnormal_detail"],
            r["action_detail"],
            r["photo_path"],
            "確認済" if r["manager_confirmed"] else "未確認",
            r["manager_name"],
            r["manager_confirmed_at"],
            item_text
        ])

    con.close()

    return Response(
        output.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=vehicle_check_records.csv"}
    )

@app.route("/backup")
def backup():
    if not os.path.exists(DB_PATH):
        flash("データベースがまだありません。", "error")
        return redirect(url_for("admin"))
    return send_file(DB_PATH, as_attachment=True, download_name="vehicle_check.db")

if __name__ == "__main__":
    init_db()
    seed()
    app.run(host="0.0.0.0", port=5000, debug=True)
