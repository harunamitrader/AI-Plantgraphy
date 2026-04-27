# AI Plantgraphy GitHub Pages 分離 実装計画

作成日: 2026-04-27  
対象: `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy`

## 目的

GitHub Pages 上に共用フロントを公開しつつ、各ユーザーが自分の自宅PC API だけを送信先に設定して利用できるようにする。

達成条件:

1. GitHub Pages 上の PWA が PC 停止中でも起動できる
2. 写真とメタ情報を端末保存できる
3. PC 復帰後に手動送信できる
4. 他ユーザーの写真や情報が、誤って開発者の PC に送信されない

## 前提構成

- GitHub Pages:
  - 静的 HTML / CSS / JS
  - PWA
  - IndexedDB 下書き保存
- 各ユーザーの自宅PC:
  - FastAPI API
  - Gemini CLI
  - SQLite / images
  - Tailscale HTTPS
- 接続先URLとアプリパスワード:
  - 各端末のローカル保存のみ
  - GitHub Pages に固定値を埋め込まない

## 実装方針

### Phase 1: 共用フロント化の安全ガード

[手順]
- API ベース URL の固定値を削除する
- GitHub Pages 上では接続先 URL 未設定のまま送信できないようにする
- 接続先 URL を `localStorage` に保存する
- 送信前に接続先 URL と接続先 PC 名を表示する

[検証]
- 新規ブラウザ環境で起動しても接続先が空である
- 接続先未設定ではアップロード送信できない
- 開発者の PC URL が初期表示されない

### Phase 2: API の自己識別情報

[手順]
- FastAPI に `GET /api/bootstrap` を追加する
- `server_name`, `server_id`, `base_url`, `gemini_model_choices` を返す
- 設定画面で接続確認結果として PC 名を表示する

[検証]
- API 接続確認で PC 名が取得できる
- 追加ページや設定ページに送信先 PC 名を表示できる

### Phase 3: API ベース URL 分離

[手順]
- `fetch('/api/...')` を共通ヘルパー経由に切り替える
- `apiUrl(path)` で絶対 URL を組み立てる
- `upload`, `pending-local`, `settings` の 3 画面を優先して移行する

[検証]
- 現行のサーバー配信下でも通常動作する
- 任意の API ベース URL を設定して送信できる

### Phase 4: GitHub Pages MVP

[手順]
- `upload`, `pending-local`, `settings` を静的HTMLとして切り出す
- Pages 配下向けに manifest / service worker / asset path を調整する
- IndexedDB 下書き保存と手動送信を維持する

[検証]
- GitHub Pages URL から 3 画面を開ける
- PC 停止中でも `追加` と `未送信` と `設定` が使える
- PC 復帰後に手動送信できる

### Phase 5: 他ページの移行

[手順]
- `index`, `plants`, `observations`, `review`, `observation_detail`, `plant_detail` を順次静的化する
- API から一覧/詳細を描画する

[検証]
- 図鑑、観察一覧、詳細ページが静的フロントから閲覧できる

## 今回の着手範囲

今回の実装では以下まで進める。

- この計画書の保存
- `GET /api/bootstrap` の追加
- API ベース URL 共通ヘルパーの追加
- `upload`, `pending-local`, `settings` の fetch を API ベース URL 対応へ変更
- 接続先 URL / 接続先 PC 名の表示と安全ガード追加

## 後続タスク

- CORS を GitHub Pages origin 対応にする
- Pages 向け静的HTMLの切り出し
- PWA manifest の Pages パス対応
- `index`, `plants`, `observations`, `review` などの静的化
