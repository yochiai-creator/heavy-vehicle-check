# 野田組 フォークリフト始業前点検

## Streamlit Cloud Secrets 設定（必須）

Settings > Secrets に以下を貼り付けてください：

```toml
ADMIN_CODE = "1224"
APP_URL = "https://your-app-name.streamlit.app"
```

※ APP_URL はデプロイ後に Streamlit Cloud で確認できるURLを入力してください。
※ ADMIN_CODE はお好みのコードに変更できます。

## デプロイ手順

1. ZIP内の3ファイルをGitHubリポジトリのルートに配置
   - `streamlit_app.py`
   - `requirements.txt`
   - `README.md`
2. Streamlit Cloud で「New app」→ リポジトリを選択
3. Main file path: `streamlit_app.py`
4. Secrets を設定して Deploy

## 注意事項

- データは SQLite（ローカルファイル）に保存されます
- Streamlit Cloud はサーバー再起動時にデータがリセットされます
- 本番運用には Supabase 等のクラウドDBへの移行を推奨します
