# 野田組 重機・車両 始業前点検 完全版

## 起動方法

1. ZIPを解凍
2. 解凍したフォルダを開く
3. コマンドプロンプトで以下を実行

```bash
pip install -r requirements.txt
python app.py
```

4. ブラウザで開く

```text
http://localhost:5000
```

## QRコード

```text
http://localhost:5000/qr
```

を開くと車両ごとのQRコードが自動生成されます。

## 機能

- 車両マスター
- QRコードで車両別点検
- 写真添付
- 異常時は使用禁止ロック
- 管理者確認で解除
- CSV出力
- DBバックアップ
- スマホ画面対応
