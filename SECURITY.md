# Security Policy

## 対象

AI Plantgraphyは、自宅PCで動かす個人向けWebアプリです。
スマホからの接続はTailscaleの利用を前提にしています。

## 公開してはいけないもの

- `.env`
- `PLANT_DEX_API_KEY`
- Discord Webhook URL
- `data/` フォルダ
- 植物写真、位置情報、個人宅が分かる写真

環境変数名は互換性のため `PLANT_DEX_` のまま残っています。
アプリ名は AI Plantgraphy です。

## 推奨設定

- `.env` の `PLANT_DEX_API_KEY` は初期値の `change-me` から変更してください。
- PCとスマホはTailscaleで接続してください。
- インターネット全体へ直接公開する運用は推奨しません。
- Gemini CLIやTailscaleのアカウントを共有PCで使う場合は、ログイン状態に注意してください。

## 報告

セキュリティ上の問題を見つけた場合は、公開Issueに秘密情報を書かず、GitHubのSecurity Advisoryまたは非公開の連絡手段を使ってください。
