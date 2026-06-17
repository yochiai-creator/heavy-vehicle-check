# 野田組 車両点検記録 DB自動修復版

管理者コード: 1224

修正:
- ValueError: list.index(x): x not in list を防止
- 古い車両区分・日本語区分・wheelLoader等を自動補正
- `\n` が文字として表示される問題を修正
- `nan` 表示を空欄化
- 起動時に車両マスターと履歴データを自動修復
- 管理者メニューから「車両マスター自動修復」を手動実行可能
- 壊れた車両データでも画面が落ちないように修正

Streamlit設定:
Main file path = streamlit_app.py
