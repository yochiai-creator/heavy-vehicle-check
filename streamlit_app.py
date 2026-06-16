
import streamlit as st
from datetime import date

st.set_page_config(page_title="野田組 車両点検記録", layout="wide")

st.title("🚜 野田組 車両点検記録")
st.write("完全版 作り直しベース")

st.subheader("点検入力")
vehicle = st.selectbox("車両", ["BH-001 / バックホウ1号","DP-001 / ダンプ1号","LT-001 / 軽トラ1号"])
d = st.date_input("点検日", value=date.today())
name = st.text_input("点検者名")

items = ["ブレーキ","タイヤ","灯火類","油漏れ・水漏れ"]
for i in items:
    st.radio(i, ["正常","異常"], horizontal=True, key=i)

st.file_uploader("異常写真（最大4枚）", accept_multiple_files=True)

if st.button("登録"):
    st.success("点検記録を登録しました")

st.divider()
st.subheader("管理者")
code = st.text_input("管理者コード", type="password")
if code == "1224":
    st.success("管理者ログインOK")
