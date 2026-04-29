# AI Plantgraphy 初回セットアップガイド

更新日: 2026-04-29  
対象リポジトリ: `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\AI-Plantgraphy`

## このガイドの目的

AI Plantgraphy は、**画面は GitHub Pages 側、解析と保存は自宅 PC 側** という構成で動きます。

使うときの入口は次の URL です。

- `https://harunamitrader.github.io/AI-Plantgraphy/app/`

この URL をスマホで開いてホーム画面に追加し、普段はそこから使います。  
自宅 PC 側は、写真の受信、Gemini CLI 解析、画像保存、図鑑データ保存のためのバックエンドとして動きます。

## なぜ Tailscale HTTPS が必要か

AI Plantgraphy の正面 UI は GitHub Pages の HTTPS ページです。  
この HTTPS の画面から自宅 PC の API や画像へ安全にアクセスするため、**バックエンド側も Tailscale HTTPS** を使います。

つまり:

- フロント: GitHub Pages の HTTPS
- バックエンド: Tailscale HTTPS

です。

## 準備するもの

- Windows PC
- スマホ
- Tailscale アカウント
- PC とスマホの両方に Tailscale をインストールしてログイン
- PC 側に Gemini CLI と AI Plantgraphy サーバー

## 安全仕様

- GitHub Pages 側には送信先 URL の固定値を埋め込みません
- 接続先 URL とアプリパスワードは、各端末のローカル保存だけで扱います
- 送信前に、接続先 URL と接続先 PC 名を確認できます
- 未送信下書きは、保存時の接続先 URL と現在の接続先 URL が一致しないと送信できません

これにより、他人の写真や情報が誤って別の PC に送られにくいようにしています。

## セットアップ全体の流れ

1. PC 側を起動する
2. Tailscale HTTPS URL を確認する
3. スマホで GitHub Pages 側を開く
4. 接続先 URL とアプリパスワードを設定する
5. ホーム画面に追加する

---

## [手順] 1. PC 側を起動する

1. Windows PC で AI Plantgraphy サーバーを起動する  
   - `C:\Users\sgmxk\Desktop\AI Plantgraphy を起動.lnk`
2. PC で Tailscale にログインしておく
3. Gemini CLI が使える状態にしておく

### [検証]

- PC ブラウザで `http://127.0.0.1:8000/settings` が開く
- 設定ページが表示される

---

## [手順] 2. Tailscale HTTPS URL を確認する

1. PC 側の AI Plantgraphy 設定ページを見る
2. Tailscale HTTPS URL を確認する
3. 例:
   - `https://desktop-l2vdrm8.tail2d3b02.ts.net/`

### [検証]

- HTTPS の URL が確認できる
- その URL をスマホから開いたとき、PC 起動中ならつながる

---

## [手順] 3. スマホで共用フロントを開く

1. スマホで次の URL を開く
   - `https://harunamitrader.github.io/AI-Plantgraphy/app/`
2. `設定` を開く

### [検証]

- GitHub Pages 側の設定画面が表示される

---

## [手順] 4. 接続先を設定する

1. `接続先URL` に、自分の PC の Tailscale HTTPS URL を入れる
2. `アプリパスワード` を入れる
3. `Geminiモデル` を選ぶ
4. `この端末に保存` を押す
5. `接続先を確認` を押す

### [検証]

- `現在の送信先` に自分の URL が出る
- `接続先PC` に自分の PC 名が出る
- `接続先を確認しました: PC名` の表示が出る

---

## [手順] 5. ホーム画面に追加する

1. スマホブラウザのメニューを開く
2. `ホーム画面に追加` を選ぶ
3. 追加後、ホーム画面アイコンから起動する
4. 少なくとも次のページを一度ずつ開く
   - `ホーム`
   - `追加`
   - `未送信`
   - `設定`

### [検証]

- ホーム画面アイコンから起動できる
- `追加` と `未送信` が開ける

---

## [手順] 6. PC 起動中の使い方

1. GitHub Pages 側から `図鑑` `観察` `確認待ち` を開く
2. 一覧や詳細、写真表示を確認する
3. `追加` から写真を送って解析する

### [検証]

- 図鑑一覧と観察一覧が表示される
- 植物詳細と観察詳細が表示される
- 写真が表示される
- 解析送信ができる

---

## [手順] 7. PC 停止中の使い方

1. ホーム画面から AI Plantgraphy を開く
2. `追加` で写真を選ぶ
3. `あとで送信する` を押す
4. `未送信` を開いて保存を確認する

### [検証]

- PC 停止中でも GitHub Pages 側の画面が開く
- `追加` と `未送信` が使える
- 未送信一覧に下書きが出る

---

## [手順] 8. PC 復帰後に手動送信する

1. PC を起動して AI Plantgraphy サーバーを立ち上げる
2. スマホで `未送信` を開く
3. `接続確認` を押す
4. `送信` または `すべて送信` を押す

### [検証]

- 送信成功後、未送信一覧から下書きが消える
- 図鑑や観察一覧に反映される

---

## よくある確認ポイント

### 1. 接続先 PC が出ない

- `接続先URL` が HTTPS で始まっているか確認する
- PC 側サーバーが起動しているか確認する
- PC とスマホの両方で Tailscale にログインしているか確認する

### 2. 写真が表示されない

- `接続先URL` が正しいか確認する
- PC 側サーバーが起動しているか確認する
- GitHub Pages 側を一度再読み込みする

### 3. 送信できない

- `アプリパスワード` が正しいか確認する
- 下書き作成時の接続先 URL と現在の接続先 URL が一致しているか確認する

### 4. PWA で開けない

- まず通常ブラウザで `https://harunamitrader.github.io/AI-Plantgraphy/app/` を開けるか確認する
- 問題なければ、ホーム画面に追加し直す

---

## 補足

- GitHub Pages 側は画面配信用です。写真や観察データの本体は保存しません
- 写真の正式保存先は各ユーザーの自宅 PC です
- 未送信下書きはスマホ端末のブラウザ保存です。ブラウザデータを消すと消えます
- PC 側の HTML 画面は保守用に残ることがありますが、通常の利用では GitHub Pages 側を使ってください
