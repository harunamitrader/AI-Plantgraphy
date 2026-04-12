# Plant Dex Tailscale セットアップ手順

## 1. これは何？

Tailscaleは、外出先のスマホから自宅PCへ安全につなぐためのアプリです。

Plant Dexでは、スマホで撮った植物写真を自宅PCのPlant Dexへ送るために使います。

```text
スマホ
  ↓ Tailscale
自宅PCのPlant Dex
```

## 2. 必要なもの

- 自宅PC
- スマホ
- Tailscaleアカウント
- PC版Tailscale
- スマホ版Tailscale
- PCで起動しているPlant Dex

## 3. PCにTailscaleを入れる

1. Tailscale公式サイトを開く
2. Windows版Tailscaleをインストールする
3. Google、Microsoft、GitHubなどのアカウントでログインする
4. Tailscaleが接続済みになっていることを確認する

## 4. スマホにTailscaleを入れる

1. AndroidならGoogle Play、iPhoneならApp Storeを開く
2. Tailscaleをインストールする
3. PCと同じアカウントでログインする
4. TailscaleをONにする

## 5. Plant Dexを起動する

PCでPlant Dexを起動します。

起動後、PCブラウザで接続ページを開きます。

```text
http://127.0.0.1:8000/connect
```

接続ページには、スマホで開くためのQRコードが表示されます。

## 6. スマホから開く

1. スマホのTailscaleをONにする
2. Plant Dexの接続ページに表示されたQRコードを読む
3. アップロード画面が開く
4. 写真を1〜3枚選んで送信する

ブラウザ内で続けて撮影したい場合は `連続カメラ` を使います。ブラウザの制約により、HTTPSまたはlocalhostでのみ使えます。TailscaleのHTTP URLで使えない場合は `通常カメラ` を使ってください。

## 連続カメラを外出先で使う

外出先で `連続カメラ` を使う場合は、Tailscale IPのHTTP URLではなく、Tailscale ServeのHTTPS URLを使います。

PCでPlant Dexを起動したあと、必要に応じて以下を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure_tailscale_https.ps1
```

成功すると以下のようなURLが表示されます。

```text
https://<PC名>.<tailnet>.ts.net/upload
```

スマホのTailscaleをONにして、このHTTPS URLを開いてください。

`/connect` ページの `Tailscale Serve` が `configured` になっていれば、表示されるQRコードもHTTPS URLを優先します。

スクリプトがタイムアウトする場合は、Tailscaleの管理画面で以下を確認してください。

- MagicDNSが有効
- HTTPS Certificatesが有効
- PCとスマホが同じtailnetに参加している

その後、もう一度 `scripts\configure_tailscale_https.ps1` を実行します。

## 7. 外出先で使う時の注意

外出先で使うには、以下が必要です。

- 自宅PCの電源が入っている
- 自宅PCがスリープしていない
- 自宅PCでPlant Dexが起動している
- 自宅PCでTailscaleが接続済み
- スマホでTailscaleがON

## 8. よくあるトラブル

### QRコードを読んでも開けない

- スマホのTailscaleがONか確認する
- PCのTailscaleが接続済みか確認する
- PCのPlant Dexが起動しているか確認する
- URLが `http://100.x.x.x:8000/` のようになっているか確認する

### 家では開けるが外で開けない

- スマホのTailscaleがOFFになっていないか確認する
- 自宅PCがスリープしていないか確認する
- 自宅PCのネット接続を確認する

### 写真を送れない

- APIキーが正しいか確認する
- 写真が1〜3枚選ばれているか確認する
- 画像サイズが大きすぎないか確認する

## 9. セキュリティ

Plant DexはTailscale経由で使うことを標準にしています。

ただし、Tailscaleを使っていてもPlant DexのAPIキーは必要です。APIキーの初期値 `change-me` は公開前に変更してください。
