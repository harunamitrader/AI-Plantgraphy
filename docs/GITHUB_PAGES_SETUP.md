# AI Plantgraphy GitHub Pages セットアップ

更新日: 2026-04-27  
対象リポジトリ: `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy`

## 目的

GitHub Pages 上に AI Plantgraphy の共用フロントを公開し、各ユーザーが自分の PC API にだけ接続して使えるようにします。

この構成では:

- Web アプリ本体は GitHub Pages から開く
- 写真とメタ情報の一時保存はスマホ端末内で行う
- 実際の解析と正式保存は各ユーザーの自宅 PC で行う

## 重要な安全仕様

- 共用フロントには送信先 URL の固定値を埋め込みません
- 接続先 URL とアプリパスワードは、各端末のローカル保存だけで扱います
- 送信前に、接続先 URL と接続先 PC 名を画面に表示します
- 未送信下書きは、保存時の送信先 URL と現在の送信先 URL が一致しないと送信できません

これにより、ほかのユーザーの写真や情報が誤って開発者の PC に送られにくい設計にしています。

## 公開後の URL

GitHub Pages を有効にすると、通常は次の URL で開けます。

- `https://harunamitrader.github.io/AI-Plantgraphy/app/`

リポジトリ名や所有者が変わる場合は URL も変わります。

## 公開手順

### [手順] 1. GitHub Pages を有効にする

1. GitHub で `AI-Plantgraphy` リポジトリを開く
2. `Settings`
3. 左メニューの `Pages`
4. `Build and deployment` の `Source` を `Deploy from a branch` にする
5. Branch を `main`
6. Folder を `/docs`
7. `Save`

### [検証]

- 数分待ってから `https://harunamitrader.github.io/AI-Plantgraphy/app/` を開く
- ホーム画面が表示される

## 初回セットアップ

### [手順] 2. PC 側を準備する

1. Windows PC で AI Plantgraphy サーバーを起動する
2. Tailscale でログインする
3. HTTPS の接続先 URL を確認する
4. アプリパスワードを把握しておく

サーバー起動ショートカット:

- `C:\Users\sgmxk\Desktop\AI Plantgraphy を起動.lnk`

### [検証]

- PC ブラウザで `http://127.0.0.1:8000/settings` が開く
- 接続ガイドに Tailscale HTTPS URL が出る

## スマホでの初回利用

### [手順] 3. 共用フロントを開く

1. スマホで次の URL を開く
   - `https://harunamitrader.github.io/AI-Plantgraphy/app/`
2. `設定` を開く
3. `接続先URL` に自分の PC の Tailscale HTTPS URL を入れる
4. `アプリパスワード` を入れる
5. `接続先を確認` を押す
6. `この端末に保存` を押す

### [検証]

- `現在の送信先` に自分の URL が出る
- `接続先PC` に自分の PC 名が出る

## PWA として追加する

### [手順] 4. ホーム画面に追加する

1. スマホブラウザのメニューから `ホーム画面に追加`
2. 追加後、ホーム画面アイコンから起動する
3. `ホーム` `追加` `未送信` `設定` を一度ずつ開く

### [検証]

- `設定` の診断で PWA / キャッシュが正常表示になる
- `未送信件数` が見える

## PC 停止中の使い方

### [手順] 5. 写真を端末保存する

1. PWA で `追加` を開く
2. 写真候補を作る
3. 1〜3枚を選ぶ
4. `あとで送信する` を押す

### [検証]

- `未送信` に保存した記録が出る
- PC が停止していても `追加` と `未送信` は開ける

## PC 復帰後の送信

### [手順] 6. 手動送信する

1. PC を起動して AI Plantgraphy サーバーを立ち上げる
2. スマホで `未送信` を開く
3. `接続確認` を押す
4. `送信` または `すべて送信` を押す

### [検証]

- 送信成功後、未送信一覧から下書きが消える
- PC 側に観察記録が作成される

## トラブル時の確認ポイント

### 1. 接続できない

- `設定` の `接続先URL` が自分の Tailscale HTTPS URL か確認する
- PC 側サーバーが起動しているか確認する
- Tailscale に PC とスマホの両方がログインしているか確認する

### 2. 送信できない

- `アプリパスワード` が一致しているか確認する
- 下書き作成時の送信先 URL と、現在の送信先 URL が一致しているか確認する

### 3. PWA で開けない

- まず通常のブラウザで `https://harunamitrader.github.io/AI-Plantgraphy/app/` が開くか確認する
- 開けたあとにホーム画面へ追加し直す

## 補足

- GitHub Pages は画面配信用であり、写真や観察データ本体は保存しません
- 写真の正式保存先は各ユーザーの PC です
- 未送信下書きはスマホ端末のブラウザ保存です。ブラウザデータを消すと消えます
