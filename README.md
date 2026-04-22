# Plant Dex

スマホで庭木・草花の写真を基本3枚、必要に応じて1〜2枚でも撮影し、自宅PC上の Gemini CLI で解析して、植物図鑑として保存・閲覧するための個人用アプリ構想です。

## まず使う

Windowsで試す場合は、こちらから始めます。

- クイックスタート: `docs\QUICK_START_WINDOWS.md`
- Tailscale手順: `docs\TAILSCALE_SETUP.md`

PowerShellで最短セットアップ:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\create_desktop_shortcut.ps1
```

その後、デスクトップの `Plant Dex を起動` を開きます。

## 現在の実装範囲

- Windows 11 Pro上で動かすFastAPIサーバー
- 写真1〜3枚のアップロードAPI
- SQLiteへの観察記録・植物データ保存
- Gemini CLI連携用サービス
- Gemini無効時の仮解析モード
- スマホから見られるWeb図鑑の最小画面
- スマホブラウザからの写真アップロード画面
- 観察記録の全件表示と検索
- 解析結果の再解析と手動修正
- 植物DBと画像のzipバックアップ
- Discord Webhook通知の下準備
- ホーム画面と設定ページ
- 設定ページでの接続QR、起動診断、バックアップ、場所ラベル管理
- Windows用初期セットアップスクリプト
- GitHub Actionsによる自動テスト

## ドキュメント

- 仕様書: `docs\SPECIFICATION.md`
- 実装計画書: `docs\IMPLEMENTATION_PLAN.md`
- Tailscale実装計画: `docs\TAILSCALE_IMPLEMENTATION_PLAN.md`
- Tailscaleセットアップ手順: `docs\TAILSCALE_SETUP.md`
- Windowsクイックスタート: `docs\QUICK_START_WINDOWS.md`
- 貢献ガイド: `CONTRIBUTING.md`
- セキュリティ: `SECURITY.md`

## 初期方針

- スマホWeb/PWAは OPPO Reno11 A / ColorOS 15 / Android 15 を初期確認対象にする
- PC側は Windows 11 Pro で FastAPI + SQLite + Gemini CLI を動かす
- 外出先からの送信は Tailscale 経由を標準とする
- Discordは主処理ではなく、解析完了通知として使う

## PCサーバーの起動

PowerShellで以下を実行します。

```powershell
cd plant-dex
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r .\server\requirements.txt
Copy-Item .\.env.example .\.env
uvicorn server.app.main:app --reload
```

起動後、以下を開きます。

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/api/health
http://127.0.0.1:8000/settings
```

## 画像1〜3枚のテスト送信

`.env` の `PLANT_DEX_API_KEY` を設定したうえで、テスト用スクリプトから送信できます。

```powershell
.\.venv\Scripts\python.exe .\scripts\upload_observation.py `
  "C:\path\to\image1.jpg" `
  "C:\path\to\image2.jpg" `
  "C:\path\to\image3.jpg" `
  --note "庭の記録"
```

初期状態では `PLANT_DEX_GEMINI_ENABLED=false` のため、Gemini CLIは実行せず仮の解析結果を保存します。Gemini CLIの呼び出し確認後、`.env` で `PLANT_DEX_GEMINI_ENABLED=true` に変更します。

Windows PowerShell 5.1 の `Invoke-RestMethod` には `-Form` がないため、multipart送信のテストは上記スクリプトを使うのが安全です。PowerShell 7以降なら `Invoke-RestMethod -Form` でも送信できます。

## スマホから使う画面

PCサーバーを `0.0.0.0` で起動している場合、同じWi-Fiのスマホから以下を開きます。

```text
http://<PCのローカルIP>:8000/
http://<PCのローカルIP>:8000/upload
```

アップロード画面では、既存写真を選ぶ場合は `写真から選ぶ`、ブラウザ内で続けて撮る場合は `連続カメラ`、端末標準のカメラを使う場合は `通常カメラ` を使います。

`連続カメラ` はブラウザのカメラAPIを使うため、HTTPSまたはlocalhostで動きます。TailscaleのHTTP URLで使えない場合は `通常カメラ` を使ってください。

外出先で `連続カメラ` を使う場合は、Tailscale ServeのHTTPS URLを使います。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure_tailscale_https.ps1
```

成功後は `/settings` のQRコードがHTTPS URLを優先します。

スクリプトがタイムアウトする場合は、Tailscale管理画面でMagicDNSとHTTPS Certificatesを有効にしてから再実行してください。
HTTPS Certificatesを有効にするとPC名とtailnet名が公開証明書ログに記録されるため、必要なら先にTailscaleのMachinesページでPC名を変更してください。

外出先で使う場合は、PCとスマホの両方でTailscaleにログインし、Plant Dexの設定ページに表示されるTailscale URLまたはQRコードを使います。

```text
http://<PCのTailscale IP>:8000/
http://<PCのTailscale IP>:8000/upload
```

## バックアップ

Web画面の `設定` からAPIキーを入力し、`zipを作成して保存` を押します。

zipには以下が入ります。

- `plants.sqlite`
- `images/`
- `manifest.json`

作成したzipは以下にも残ります。

```text
data\exports
```

## 運用ログ

画像受信、解析開始、解析完了、解析失敗、手動修正、削除、バックアップ作成は以下に追記されます。

```text
data\logs\server.log
```

`PLANT_DEX_DISCORD_WEBHOOK_URL` を設定すると、解析成功と解析失敗をDiscordへ通知できます。

## Gemini CLI解析を有効化する

Gemini CLIが以下のように使えることを確認します。

```powershell
gemini --version
gemini --help
```

`.env` を編集して、以下に変更します。

```text
PLANT_DEX_GEMINI_ENABLED=true
PLANT_DEX_GEMINI_COMMAND=gemini
PLANT_DEX_GEMINI_MODEL=gemini-3-flash-preview
PLANT_DEX_GEMINI_MODEL_OPTIONS=auto-gemini-3,auto-gemini-2.5,gemini-3.1-pro-preview,gemini-3-flash-preview,gemini-2.5-pro,gemini-2.5-flash,gemini-2.5-flash-lite
```

サーバーを再起動します。

```powershell
uvicorn server.app.main:app --reload
```

その後、もう一度画像1〜3枚を送信します。Gemini CLIには次の形式でプロンプトを渡します。

```text
gemini --output-format text -p "<画像1〜3枚のパスを含む植物判定プロンプト>"
```

Geminiの出力がJSONとして解釈できれば、図鑑ページに実際の植物名と解析JSONが保存されます。

`PLANT_DEX_GEMINI_MODEL` はPC側の既定モデルです。初期値は `gemini-3-flash-preview` です。空欄にするとGemini CLI側の既定モデルを使います。
スマホのアップロード画面と観察記録の再解析画面では、`PLANT_DEX_GEMINI_MODEL_OPTIONS` に並べたモデルからその場で選べます。

## テスト

AIで確認できる範囲のサービス層・主要画面の自動テストは、以下で実行できます。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s .\server\tests -p "test_*.py"
```

または:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

構文チェックを広めに行う場合は、以下も実行します。

```powershell
.\.venv\Scripts\python.exe -m compileall .\server .\scripts
```

## 配布zipを作る

`.env`、`.venv`、`data` を除いたzipを作る場合は以下を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\package_release.ps1
```

zipは `dist` に作成されます。

## ライセンス

MIT Licenseです。詳細は `LICENSE` を確認してください。
