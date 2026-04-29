# AI Plantgraphy GitHub Pages 統一フロント 実装計画

更新日: 2026-04-29  
対象: `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy`

## 目的

AI Plantgraphy のユーザー向け画面を GitHub Pages 側に統一し、各ユーザーの自宅 PC は Tailscale HTTPS 経由のバックエンドとしてだけ使う構成へ移行する。

この計画で達成したいこと:

1. ユーザーが普段使う URL を GitHub Pages 側 1 つに統一する
2. PC 停止中でも GitHub Pages 側の PWA を開いて写真の下書き保存ができる
3. PC 起動中は GitHub Pages 側から HTTPS の API を通して図鑑・観察・画像・解析結果を読み書きできる
4. 送信先 URL の固定埋め込みを避け、他ユーザーの写真や情報が誤って開発者 PC に送られないようにする
5. 初回セットアップ手順を非エンジニアにもわかりやすく整える

## 最終構成

### フロント

- GitHub Pages
  - `https://harunamitrader.github.io/AI-Plantgraphy/app/`
  - PWA
  - IndexedDB 下書き保存
  - 図鑑 / 観察 / 追加 / 未送信 / 確認待ち / 設定

### バックエンド

- 各ユーザーの自宅 PC
  - FastAPI API
  - Gemini CLI
  - SQLite
  - 画像保存
  - Tailscale HTTPS URL

### 接続方式

- フロント: GitHub Pages の HTTPS
- バックエンド: Tailscale HTTPS
- アプリ内設定:
  - 接続先 URL
  - アプリパスワード
  - Gemini モデル

## 設計原則

1. GitHub Pages 側に送信先 URL の初期値を埋め込まない
2. 接続先 URL とアプリパスワードは各端末ローカル保存のみ
3. GitHub Pages 側の画面で、送信先 URL と接続先 PC 名を常に確認できるようにする
4. PC 側 HTML は残してもよいが、ユーザー向けの主導線には使わない
5. 画像 URL や詳細 URL は GitHub Pages 側で解決できる相対パスまたは接続先基準 URL を返す

## 現在の到達点

以下は着手済み:

- `docs/app` に GitHub Pages 用の静的フロントがある
- `settings / upload / pending-local / plants / plant / observations / observation / review` の静的ページがある
- `GET /api/bootstrap` があり、接続先 PC 名やモデル候補を返せる
- GitHub Pages 側から PC API を叩くための CORS は導入済み
- 接続先 URL 未設定時の安全ガードは導入済み
- 下書き保存と手動送信は GitHub Pages 側で動く

未整理または追加対応が必要な点:

- GitHub Pages 側を唯一の正面 UI として見せる導線整理
- PC 側ページリンクの削減
- 画像・詳細・一覧の相対 URL ルール統一
- 初回セットアップ案内の整理
- README / 仕様書 / 画面内文言の統一

## 実装計画

### Phase 1: 正面 UI を GitHub Pages 側へ統一

[手順]
- GitHub Pages 側のヘッダーとナビを正面 UI として整える
- `ホーム / 図鑑 / 観察 / 追加 / 未送信 / 確認待ち / 設定` をすべて GitHub Pages 側で回遊できるようにする
- GitHub Pages 側から PC 側 HTML を直接開く補助導線は削除または非表示にする
- PC 側 HTML は保守用として残しても、通常導線からは外す

[検証]
- GitHub Pages 側だけで主要メニューを一周できる
- PC 側 HTML を知らなくても通常利用できる

### Phase 2: API と画像 URL の統一

[手順]
- 一覧 API と詳細 API が返す `image_urls`, `representative_image_url`, `photo_urls` を相対パス基準で統一する
- GitHub Pages 側の JS で、相対パスを接続先 URL に解決する処理を共通化する
- 一覧カード・詳細カード・モーダル表示のすべてで同じ URL 解決を使う
- `127.0.0.1` や `base_url` 固定値がクライアントへ漏れないようにする

[検証]
- GitHub Pages 側の図鑑一覧で既存写真が表示される
- GitHub Pages 側の植物詳細・観察詳細で既存写真が表示される
- スマホ実機で画像クリック拡大が動く

### Phase 3: データ表示の整合性を取る

[手順]
- GitHub Pages 側の植物詳細・観察詳細が、PC 側 DB にあるデータだけをそのまま表示するようにする
- 未保存のプロフィール文は「未登録」扱いで表示し、自動補完は行わない
- GitHub Pages 側で表示する項目名と PC 側の元データ構造を揃える
- 観察レコードと植物レコードの責務を再確認する

[検証]
- 既存データがある植物では説明文がそのまま表示される
- 既存データがない植物では、誤って自動生成されず空欄または未登録表示になる

### Phase 4: オフライン下書き機能の実利用調整

[手順]
- `追加` 画面で写真・メモ・場所ラベル・モデルを IndexedDB へ保存する流れを最終確認する
- `未送信` 一覧で個別送信・一括送信・削除を調整する
- 下書き作成時の接続先 URL と現在の接続先 URL が不一致なら送信を止める
- GitHub Pages 側 PWA と通常ブラウザの両方で確認する

[検証]
- PC 停止中でも `追加` と `未送信` が使える
- PC 復帰後に HTTPS 接続先へ手動送信できる
- 他人の接続先 URL に変わっている場合は送信できない

### Phase 5: HTTPS 前提のセットアップ導線整理

[手順]
- ドキュメントと設定画面で、PC 側は Tailscale HTTPS が必要であることを明記する
- HTTP ではなく HTTPS を使う理由を短く説明する
- 接続確認時に、接続先 URL と PC 名が正しければ利用開始できることを明示する
- 初回セットアップを「PC 側準備」「スマホ側設定」「ホーム画面追加」の 3 段階に分ける

[検証]
- セットアップ文書だけ読んでも、必要な作業順がわかる
- 非エンジニアでも「何をどこに入れるか」が迷いにくい

### Phase 6: ドキュメント統一

[手順]
- `README.md` を GitHub Pages 正面構成に合わせて更新する
- `docs/SPECIFICATION.md` に新構成の利用フローと技術構成を追記する
- `docs/GITHUB_PAGES_SETUP.md` を初回セットアップの主文書として整える
- 画面内の文言も `接続先URL`, `接続先PC`, `アプリパスワード` などで統一する

[検証]
- README と仕様書と画面文言に矛盾がない
- GitHub Pages 側を本体 UI として説明している

### Phase 7: 最終確認

[手順]
- PC 起動中:
  - GitHub Pages 側で一覧・詳細・画像・送信が使えるか確認する
- PC 停止中:
  - GitHub Pages 側 PWA が起動し、下書き保存できるか確認する
- PC 復帰後:
  - 未送信から手動送信できるか確認する
- 主要ケースを実機で再確認する

[検証]
- GitHub Pages 側だけで通常利用フローが完結する
- PC 側 HTML を使わなくても困らない

## 実装時の注意

- 自動生成によるプロフィール補完は入れない
- 既存 DB にない情報は、勝手に埋めずそのまま扱う
- 送信先 URL の初期値は常に空のままにする
- 開発者 PC 向け URL やパスワードをリポジトリへ埋め込まない

## 直近の優先順

1. GitHub Pages 側から見た画像と詳細表示の整合性を取る
2. PC 側 HTML への導線を整理し、GitHub Pages 側を本体 UI に寄せる
3. 初回セットアップ文書を HTTPS 前提でわかりやすく書き直す
4. README / 仕様書へ反映する

## 完了条件

以下が揃ったら、この移行は完了とする。

1. GitHub Pages 側の URL だけを案内すればユーザーが使い始められる
2. 各ユーザーは自分の Tailscale HTTPS URL とアプリパスワードだけ設定すればよい
3. 図鑑 / 観察 / 追加 / 未送信 / 確認待ち / 設定 が GitHub Pages 側だけで使える
4. PC 側は API / 画像配信 / Gemini CLI / DB のバックエンドとしてのみ機能する
