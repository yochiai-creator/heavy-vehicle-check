# 野田組 重機・車両 始業前点検 Streamlit版

## Streamlit設定

- Main file path: streamlit_app.py

## 必要ファイル

- streamlit_app.py
- requirements.txt

## 機能

- QRコードで車両自動選択
- 車両マスター
- 点検入力
- 異常時の写真必須
- 写真はSQLite DB内に保存
- 異常時は使用禁止ロック
- 管理者確認でロック解除
- 異常一覧
- 履歴検索
- CSV出力
- DBバックアップ

## QRコード

QRコード発行画面で、今開いているStreamlitアプリのURLを貼ってください。
例:
https://heavy-vehicle-check-xxxx.streamlit.app

車両別に
https://heavy-vehicle-check-xxxx.streamlit.app/?vehicle=FL-001
のQRを作ります。
