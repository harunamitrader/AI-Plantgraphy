# Contributing

Plant Dexへの改善提案や不具合報告を歓迎します。

## 開発環境

Windowsの場合:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
```

## テスト

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

## Pull Requestの目安

- 変更内容を小さく分ける
- 実データ、`.env`、画像、SQLite DBをコミットしない
- UI変更はスマホ幅でも確認する
- Geminiのプロンプトを変えた場合は、期待するJSON構造が崩れないか確認する

## セキュリティ

APIキー、Discord Webhook URL、個人の植物写真、位置情報をIssueやPull Requestに貼らないでください。
