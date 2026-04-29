# AI Plantgraphy 図鑑 / 観察 データ閲覧キャッシュ設計

更新日: 2026-04-29  
対象: `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy`

## 目的

GitHub Pages 側の共用フロントで、PC サーバーが停止中でも **最後に取得できた図鑑 / 観察データを見返せる** ようにする。

今回の対象は「閲覧キャッシュ」であり、以下は目的に含めない。

- オフライン中の再解析
- オフライン中の削除
- オフライン中の手動修正送信
- キャッシュからの完全な図鑑復元

## 方針

1. まずは **一覧と直近で開いた詳細** だけをキャッシュする
2. 書き込み操作はオフラインでは行わず、未接続バナーを出して止める
3. オフライン時は `オフライン表示中 / 最新ではありません` を明示する
4. 画像は全部キャッシュせず、まずは **代表画像 1 枚** と **最近開いた詳細ページ内の画像** に絞る
5. 保存先は `IndexedDB` を使う

## 対象ページ

### キャッシュ対象

- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\plants.html`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\observations.html`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\review.html`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\plant.html`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\observation.html`

### 今回は対象外

- `upload.html`
- `pending-local.html`
- `settings.html`

これらはすでにオフライン時の役割が別に定まっているため、閲覧キャッシュの主対象から外す。

## 保存するデータ

### 1. 図鑑一覧キャッシュ

キー:
- `plants_index`

内容:
- 最終取得日時
- 植物一覧 JSON
- 表示用の最小メタ情報
  - `plant_id`
  - `common_name_ja`
  - `scientific_name`
  - `observation_count`
  - `representative_image_url`
  - `updated_at` 相当の比較用値

### 2. 観察一覧キャッシュ

キー:
- `observations_index`

内容:
- 最終取得日時
- 観察一覧 JSON
- 表示用の最小メタ情報
  - `observation_id`
  - `common_name_ja`
  - `scientific_name`
  - `status`
  - `confidence`
  - `captured_at`
  - `representative_image_url`

### 3. 確認待ち一覧キャッシュ

キー:
- `review_index`

内容:
- 最終取得日時
- 確認待ち一覧 JSON

### 4. 植物詳細キャッシュ

キー:
- `plant_detail::<plant_id>`

内容:
- 最終取得日時
- `plant` JSON
- `observations` JSON
- `photo_urls`

### 5. 観察詳細キャッシュ

キー:
- `observation_detail::<observation_id>`

内容:
- 最終取得日時
- 観察詳細 JSON
- 解析結果 JSON
- 候補
- 写真 URL 群

## 画像キャッシュ方針

### 方針

- API の JSON と一緒に画像そのものまでは全件保存しない
- まずはブラウザ標準キャッシュに任せる
- 必要なら後で `IndexedDB` に Blob 保存を追加する

### 理由

- 容量増加を抑える
- 実装を小さく始められる
- まずはテキストと一覧の閲覧可否が重要

### 将来拡張候補

- 代表画像 1 枚だけ Blob キャッシュ
- 最近開いた植物詳細 / 観察詳細の画像だけ保存

## オフライン時の表示ルール

### 一覧ページ

#### サーバー接続成功
- 最新データを API から取得
- 画面を更新
- キャッシュを上書き保存

#### サーバー接続失敗
- キャッシュあり:
  - キャッシュを表示
  - 上部に `オフライン表示中 / 最新ではありません` バナーを表示
  - `最終更新: yyyy-mm-dd hh:mm` を表示
- キャッシュなし:
  - 既存どおり未接続バナー
  - `まだ保存済みデータがありません` を表示

### 詳細ページ

#### サーバー接続成功
- 最新データを取得
- 画面を更新
- 詳細キャッシュを保存

#### サーバー接続失敗
- キャッシュあり:
  - キャッシュを表示
  - 編集・再解析・削除などの操作は無効化
  - `オフライン表示中 / 最新ではありません` を表示
- キャッシュなし:
  - 未接続バナーのみ表示

## オフライン時に止める操作

- 再解析
- 削除
- 修正して保存
- 場所ラベル更新

ただし、`あとで送信する` と `未送信一覧` は引き続き利用可能とする。

## データ更新タイミング

### 保存タイミング

- `plants.html` をオンラインで開いた直後
- `observations.html` をオンラインで開いた直後
- `review.html` をオンラインで開いた直後
- `plant.html?id=...` をオンラインで開いた直後
- `observation.html?id=...` をオンラインで開いた直後

### 無効化タイミング

明示的な期限切れは入れず、まずは `lastFetchedAt` を表示するだけにする。

理由:
- 古くても見られた方がよい
- 期限ロジックを先に入れると複雑になる

## 保存構造

新規ファイル候補:
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\static\view-cache.js`

責務:
- IndexedDB 初期化
- 保存 / 取得 / 削除
- キー生成
- メタ情報管理

想定ストア:
- `pages_view_cache`
  - `entries`
  - key: `plants_index`, `observations_index`, `plant_detail::<id>` など

1 レコード例:

```json
{
  "key": "plants_index",
  "savedAt": "2026-04-29T12:00:00+09:00",
  "kind": "plants_index",
  "payload": {
    "plants": []
  }
}
```

## UI 追加案

### 一覧ページ

- 上部にキャッシュバナー
  - `オフライン表示中`
  - `最終更新 2026-04-29 12:00`
- オンライン復帰後に再読込したら自動で消える

### 詳細ページ

- タイトル直下にキャッシュバナー
- ボタン群の上に `PC接続中のみ操作できます`

## 容量方針

初期段階では、件数制限は入れずにテキスト中心で保存する。  
将来、画像 Blob を保存し始める段階で次を追加する。

- 一覧は 1 世代のみ保持
- 詳細は最近 20 件まで
- 古いキャッシュから削除

## 実装計画

### Phase 1: キャッシュユーティリティ作成

[手順]
- `view-cache.js` を追加
- IndexedDB の `saveEntry / loadEntry / removeEntry` を実装
- 一覧キーと詳細キーのルールを定義

[検証]
- ブラウザから一覧 JSON を保存・取得できる
- 既存の下書き保存と衝突しない

### Phase 2: 一覧ページへ適用

[手順]
- `plants.html` にキャッシュ保存を追加
- オフライン時はキャッシュ表示へフォールバック
- `observations.html` と `review.html` に同じ仕組みを適用

[検証]
- オンラインで一度開いた後、PC停止中でも一覧が見られる
- キャッシュがないときは未接続表示になる

### Phase 3: 詳細ページへ適用

[手順]
- `plant.html` と `observation.html` にキャッシュ保存を追加
- オフライン時はキャッシュ表示へフォールバック
- オフライン時は操作ボタンを無効化

[検証]
- オンラインで一度開いた詳細は、PC停止中でも再表示できる
- オフライン時に再解析や削除が走らない

### Phase 4: 表示メッセージ整理

[手順]
- オフライン用バナー文言を統一
- `最終更新` 表示を追加
- `最新ではありません` の文言を一覧・詳細で揃える

[検証]
- ユーザーが「壊れている」のではなく「オフライン表示」だと理解できる

## 既存コードへの影響範囲

追加中心で進める。既存サーバー API の変更は原則不要。

主に触るファイル:
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\plants.html`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\observations.html`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\review.html`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\plant.html`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\observation.html`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\static\app.js`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\static\style.css`
- `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy\docs\app\static\view-cache.js`（新規）

## 完了条件

以下が揃えば、この機能は完了とする。

1. 図鑑一覧を一度オンラインで開けば、PC停止中でも見返せる
2. 観察一覧を一度オンラインで開けば、PC停止中でも見返せる
3. 一度開いた植物詳細 / 観察詳細を PC 停止中でも見返せる
4. オフライン時は更新操作が止まり、誤操作しない
5. ユーザーに `最新ではありません` が明確に伝わる
