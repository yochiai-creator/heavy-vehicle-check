
import streamlit as st
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO

st.set_page_config(page_title="重機・車両 始業前点検", page_icon="🚜", layout="centered")

VEHICLE_LABELS = {
    "forklift": "フォークリフト",
    "wheel_loader": "ホイールローダー",
    "dump": "ダンプ",
}

CHECK_ITEMS = {
    "forklift": [
        ("制動装置・ブレーキの効き", "作業開始前点検"),
        ("操縦装置・ハンドル操作", "作業開始前点検"),
        ("荷役装置・油圧装置・油漏れ", "作業開始前点検"),
        ("フォーク・マスト・チェーンの損傷", "安全確認"),
        ("タイヤ・ホイール・ナットの緩み", "作業開始前点検"),
        ("前照灯・方向指示器・警報装置", "作業開始前点検"),
        ("燃料・バッテリー・充電状態", "日常確認"),
    ],
    "wheel_loader": [
        ("ブレーキの効き", "作業開始前点検"),
        ("クラッチ・走行操作", "作業開始前点検"),
        ("バケット・アーム・ピンの損傷", "安全確認"),
        ("油圧装置・油漏れ", "安全確認"),
        ("タイヤ・ホイール・ナットの緩み", "安全確認"),
        ("灯火類・警報ブザー・バックブザー", "安全確認"),
        ("燃料・エンジンオイル・冷却水", "日常確認"),
    ],
    "dump": [
        ("ブレーキペダルの踏みしろ・効き", "日常点検"),
        ("タイヤ空気圧・亀裂・異常摩耗", "日常点検"),
        ("ホイールナットの緩み", "日常点検"),
        ("灯火類・方向指示器・反射器", "日常点検"),
        ("エンジンオイル・冷却水・ブレーキ液", "日常点検"),
        ("荷台・あおり・ダンプ装置・油漏れ", "安全確認"),
        ("車検証・自賠責・運行前確認", "運行前確認"),
    ],
}

if "records" not in st.session_state:
    st.session_state.records = []

st.title("🚜 重機・車両 始業前点検")
st.caption("フォークリフト・ホイールローダー・ダンプ対応 / Streamlit版")

tab_check, tab_history, tab_qr = st.tabs(["点検", "履歴・出力", "QR共有"])

with tab_check:
    st.subheader("基本情報")
    vehicle_type = st.selectbox("車種", list(VEHICLE_LABELS.keys()), format_func=lambda x: VEHICLE_LABELS[x])
    vehicle_name = st.text_input("車両番号・車両名", placeholder="例：リフト1号 / ダンプ2号")
    inspector = st.text_input("点検者名", placeholder="氏名")
    meter = st.text_input("メーター・走行距離・アワーメーター", placeholder="例：1234h / 56000km")

    st.subheader("点検項目")
    statuses = {}
    for idx, (label, note) in enumerate(CHECK_ITEMS[vehicle_type]):
        with st.container(border=True):
            st.markdown(f"**{label}**")
            st.caption(note)
            statuses[label] = st.radio(
                "判定",
                ["良好", "異常あり", "対象外"],
                horizontal=True,
                key=f"{vehicle_type}_{idx}",
            )

    has_abnormal = any(v == "異常あり" for v in statuses.values())
    abnormal_detail = ""
    action_detail = ""
    photo = None

    if has_abnormal:
        st.error("異常ありの項目があります。この車両は使用不可として記録します。")
        abnormal_detail = st.text_area("異常内容 ※必須", placeholder="どこが、どう悪いか")
        action_detail = st.text_area("対応内容 ※必須", placeholder="使用停止、修理依頼、管理者報告など")
        photo = st.file_uploader("写真添付 ※必須", type=["jpg", "jpeg", "png", "heic"])

    usable = not has_abnormal
    st.success("判定：使用可") if usable else st.error("判定：使用不可")

    if st.button("点検記録を保存", type="primary", use_container_width=True):
        if not vehicle_name or not inspector:
            st.warning("車両番号・車両名、点検者名を入力してください。")
        elif has_abnormal and (not abnormal_detail or not action_detail or photo is None):
            st.warning("異常ありの場合は、異常内容・対応内容・写真添付が必須です。")
        else:
            record = {
                "日時": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                "車種": VEHICLE_LABELS[vehicle_type],
                "車両名": vehicle_name,
                "点検者": inspector,
                "メーター": meter,
                "使用可否": "使用可" if usable else "使用不可",
                "管理者確認": "未確認",
                "管理者名": "",
                "異常内容": abnormal_detail,
                "対応内容": action_detail,
                "写真": photo.name if photo else "",
                "点検項目": " / ".join([f"{k}:{v}" for k, v in statuses.items()]),
            }
            st.session_state.records.insert(0, record)
            st.success("点検記録を保存しました。")

with tab_history:
    st.subheader("履歴・管理者確認")
    if not st.session_state.records:
        st.info("まだ点検記録がありません。")
    else:
        manager_name = st.text_input("管理者名", placeholder="管理者確認に使用")
        for i, record in enumerate(st.session_state.records):
            with st.container(border=True):
                st.markdown(f"**{record['日時']} / {record['車種']} / {record['車両名']}**")
                st.write(f"点検者：{record['点検者']}")
                st.success("使用可") if record["使用可否"] == "使用可" else st.error("使用不可")
                if record["使用可否"] == "使用不可":
                    st.write(f"異常内容：{record['異常内容']}")
                    st.write(f"対応内容：{record['対応内容']}")
                    st.write(f"写真：{record['写真']}")
                st.write(f"管理者確認：{record['管理者確認']}")
                if record["使用可否"] == "使用不可" and record["管理者確認"] == "未確認":
                    if st.button("管理者確認", key=f"confirm_{i}"):
                        if not manager_name:
                            st.warning("管理者名を入力してください。")
                        else:
                            st.session_state.records[i]["管理者確認"] = "確認済"
                            st.session_state.records[i]["管理者名"] = manager_name
                            st.rerun()

        df = pd.DataFrame(st.session_state.records)
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("CSVダウンロード", data=csv, file_name="始業前点検記録.csv", mime="text/csv", use_container_width=True)

with tab_qr:
    st.subheader("QRコード共有")
    url = st.text_input("共有URL", placeholder="例：https://xxxx.streamlit.app")
    if st.button("QRコード作成", use_container_width=True):
        if not url:
            st.warning("URLを入力してください。")
        else:
            img = qrcode.make(url)
            buf = BytesIO()
            img.save(buf, format="PNG")
            st.image(buf.getvalue(), caption=url, width=260)
            st.download_button("QR画像ダウンロード", data=buf.getvalue(), file_name="始業前点検アプリ_QR.png", mime="image/png", use_container_width=True)

st.caption("※このアプリは始業前点検記録用です。年次検査・月例検査・特定自主検査は別途管理してください。")
