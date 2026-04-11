# Plant Dex Tailscale 実装計画

## 1. 方針

Plant Dex の外出先利用は Tailscale を標準ルートにする。

Plant Dex は自宅PC上の Gemini CLI とローカル保存を中核にするため、クラウド公開型よりも「自分の端末だけが入れるプライベートネットワーク」が合っている。Tailscale を使うことで、スマホから自宅PCの Plant Dex に安全にアクセスできる。

```text
外出先のスマホ
  ↓ Tailscale
自宅PCの Plant Dex
  ↓
Gemini CLI / SQLite / data/images
```

## 2. 非目的

初期のTailscale対応では以下をやらない。

- Cloudflare Tunnel対応
- ngrokなど一時公開サービス対応
- 独自ドメイン公開
- 複数ユーザー向け公開ホスティング
- ネイティブAndroidアプリ必須化
- Tailscaleの自動インストール

## 3. 目標体験

非エンジニアでも以下の流れで使える状態を目指す。

```text
1. PCにPlant Dexを入れる
2. PCとスマホにTailscaleを入れる
3. 両方で同じTailscaleアカウントにログインする
4. PCでPlant Dexを起動する
5. Plant Dexの接続ページに出たQRコードをスマホで読む
6. 外出先でも写真を3枚送信できる
```

## 4. 追加する画面

### 4.1 接続ページ `/connect`

PCブラウザで開く接続ガイド画面。

表示内容:

- Plant Dexの起動状態
- Gemini CLIの利用状態
- APIキー設定状態
- ローカルWi-Fi用URL
- Tailscale用URL
- Tailscale用QRコード
- スマホ向けアップロードURL
- 簡単な手順
- トラブル時の確認項目

### 4.2 スマホ用接続カード

`/connect` 内に以下のカードを出す。

```text
外出先で使う
http://<tailscale-host-or-ip>:8000/upload
[QRコード]
```

同じ画面に図鑑トップのQRも置く。

```text
図鑑を見る
http://<tailscale-host-or-ip>:8000/
[QRコード]
```

## 5. URL検出方針

### 5.1 ローカルWi-Fi URL

Windows PCのIPv4アドレスから候補を検出する。

対象:

- `192.168.x.x`
- `10.x.x.x`
- `172.16.x.x` から `172.31.x.x`

例:

```text
http://192.168.0.3:8000/
http://192.168.0.3:8000/upload
```

### 5.2 Tailscale URL

Tailscaleの標準IP範囲である `100.64.0.0/10` のIPv4アドレスを候補として検出する。

例:

```text
http://100.80.12.34:8000/
http://100.80.12.34:8000/upload
```

### 5.3 MagicDNS

初期実装ではMagicDNS名の自動検出は必須にしない。

理由:

- 環境差がある
- Tailnet名を確実に取得するにはTailscale CLI依存が強くなる
- まずはIPベースのQRで十分使える

将来対応:

- `tailscale status --json` が使える場合に端末名やDNS名を取得
- `http://<device-name>:8000/` または `http://<device-name>.<tailnet>.ts.net:8000/` を表示

## 6. サーバー側API

### 6.1 GET `/api/connectivity`

接続ページ用の診断情報を返す。

Response例:

```json
{
  "server": {
    "port": 8000,
    "base_url": "http://127.0.0.1:8000"
  },
  "local_urls": [
    "http://192.168.0.3:8000/"
  ],
  "tailscale_urls": [
    "http://100.80.12.34:8000/"
  ],
  "upload_urls": {
    "local": [
      "http://192.168.0.3:8000/upload"
    ],
    "tailscale": [
      "http://100.80.12.34:8000/upload"
    ]
  },
  "checks": {
    "gemini_cli": "ok",
    "api_key": "set",
    "tailscale_ip": "found"
  }
}
```

### 6.2 GET `/connect`

Jinjaテンプレートで接続ガイドを表示する。

## 7. QRコード実装

### 7.1 初期方針

サーバー側でQRコード画像を生成してHTMLに埋め込む。

候補ライブラリ:

- `qrcode`
- `pillow`

追加依存:

```text
qrcode[pil]
```

### 7.2 QRコード生成API

`/connect` 画面内ではdata URLとして埋め込む。

保存ファイルは作らない。

```text
data:image/png;base64,...
```

### 7.3 QR対象URL

優先順位:

1. Tailscale upload URL
2. Tailscale top URL
3. Local upload URL
4. Local top URL

Tailscale IPが見つからない場合は、Tailscale欄にセットアップ案内を出す。

## 8. 起動スクリプト改善

### 8.1 既存ショートカット

既存:

```text
C:\Users\sgmxk\Desktop\Plant Dex を起動.lnk
```

起動対象:

```text
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\scripts\start_plant_dex.ps1
```

### 8.2 改善内容

- サーバー起動後に `/connect` を開く
- 8000番ポートが使えない場合は分かりやすいエラーを出す
- Tailscale IPが見つかる場合はコンソールにもURLを表示する
- PCブラウザで接続ページを開く

起動後のユーザー体験:

```text
Plant Dexを起動
  ↓
PCブラウザで /connect が開く
  ↓
スマホでQRコードを読む
```

## 9. Tailscaleセットアップガイド

### 9.1 `/connect` 内の短い手順

画面には最小限だけ表示する。

```text
1. PCとスマホにTailscaleを入れる
2. 両方で同じアカウントにログインする
3. スマホでTailscaleをONにする
4. QRコードを読む
```

### 9.2 詳細ドキュメント

追加するファイル:

```text
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\docs\TAILSCALE_SETUP.md
```

内容:

- Tailscaleとは何か
- Windowsへのインストール
- Android/iPhoneへのインストール
- 同じアカウントでログイン
- PCのTailscale IP確認
- Plant DexのQRを読む
- よくあるトラブル

## 10. トラブル診断

`/connect` に以下の診断を表示する。

| 項目 | OK条件 | NG時の表示 |
| --- | --- | --- |
| Plant Dex | `/api/health` が返る | サーバーが起動していません |
| Gemini CLI | `gemini --version` 相当が通る | Gemini CLIが見つかりません |
| APIキー | 初期値以外か確認 | APIキーを変更してください |
| Tailscale IP | `100.64.0.0/10` のIPがある | Tailscaleにログインしてください |
| ローカルIP | プライベートIPがある | Wi-Fi接続を確認してください |

## 11. セキュリティ方針

- Tailscaleを標準アクセス経路にする
- APIキー認証は継続する
- `0.0.0.0` で起動するが、公開URLはTailscale経由を推奨する
- Cloudflare Tunnelは初期導線から外す
- APIキーの初期値 `change-me` は接続ページで警告する

## 12. 実装ステップ

### Step 1: 接続情報サービス

追加:

```text
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\server\app\services\connectivity.py
```

実装:

- IPv4アドレス列挙
- ローカルIP判定
- Tailscale IP判定
- URL生成
- Gemini CLI簡易チェック
- APIキー状態チェック

### Step 2: QRコードサービス

追加:

```text
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\server\app\services\qr_code.py
```

実装:

- URL文字列をPNG QRに変換
- base64 data URLとして返す

### Step 3: APIと画面

追加/変更:

```text
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\server\app\main.py
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\server\app\web\templates\connect.html
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\server\app\web\static\style.css
```

実装:

- `GET /connect`
- `GET /api/connectivity`
- QRカードUI
- 診断カードUI

### Step 4: 起動スクリプト

変更:

```text
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\scripts\start_plant_dex.ps1
```

実装:

- 起動後に `/connect` を開く
- コンソールにTailscale URLを表示する

### Step 5: ドキュメント

追加/変更:

```text
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\docs\TAILSCALE_SETUP.md
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\README.md
```

## 13. 検証計画

### 13.1 PC単体

- `/connect` が開く
- ローカルIPが表示される
- Tailscale未導入時に分かりやすい案内が出る
- QRコード画像が表示される

### 13.2 Tailscale導入後

- `100.x.x.x` のURLが表示される
- スマホのTailscaleをONにしてQRコードから `/upload` が開く
- モバイル回線から写真3枚を送信できる
- 解析完了後に詳細ページへ移動できる

### 13.3 セキュリティ

- APIキーなしのアップロードが拒否される
- APIキー初期値の場合に警告が出る
- Tailscale OFFのスマホから `100.x.x.x` URLへ接続できない

## 14. 完了条件

- `/connect` にTailscale用URLとQRコードが表示される
- Tailscale未設定時にも次に何をすればよいか分かる
- スマホからQRコードでアップロード画面を開ける
- 外出先のモバイル回線から画像3枚を送信できる
- READMEからCloudflare Tunnel前提の説明が消え、Tailscale推奨に変わっている
