# Contributing

AI Plantgraphyへの改善提案、不具合報告、ドキュメント修正を歓迎します。

## 参加しやすい形

- 使ってみて分かりにくかった手順をIssueで教える
- スマホ表示の崩れや操作しづらい部分を報告する
- READMEやセットアップ手順を読みやすく直す
- 小さなバグ修正をPull Requestで送る

## 開発環境

Windowsの場合:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
```

## テスト

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
.\.venv\Scripts\python.exe -m compileall .\server .\scripts
```

## Pull Requestの目安

- 変更内容を小さく分ける
- 実データ、`.env`、画像、SQLite DBをコミットしない
- UI変更はPC幅とスマホ幅の両方で確認する
- Geminiのプロンプトを変えた場合は、期待するJSON構造が崩れないか確認する

## セキュリティ

アプリパスワード、Gemini APIキー、Discord Webhook URL、個人の植物写真、位置情報をIssueやPull Requestに貼らないでください。
