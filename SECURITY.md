# Security Policy

## 対象

Plant Dexは、自宅PCで動かす個人向けアプリです。スマホからの接続はTailscaleの利用を前提にしています。

## 注意点

- `.env` を公開しないでください。
- `PLANT_DEX_API_KEY` は初期値の `change-me` から変更してください。
- Discord Webhook URLを公開しないでください。
- 写真や位置情報を含む `data/` フォルダを公開しないでください。
- インターネット全体へ直接公開する運用は推奨しません。

## 報告

セキュリティ上の問題を見つけた場合は、公開Issueに秘密情報を書かず、GitHubのSecurity Advisoryまたは非公開の連絡手段を使ってください。
