# Plant Dex

スマホで庭木・草花の写真を3枚撮影し、自宅PC上の Gemini CLI で解析して、植物図鑑として保存・閲覧するための個人用アプリ構想です。

## 現在の実装範囲

- Windows 11 Pro上で動かすFastAPIサーバー
- 写真3枚のアップロードAPI
- SQLiteへの観察記録・植物データ保存
- Gemini CLI連携用サービス
- Gemini無効時の仮解析モード
- スマホから見られるWeb図鑑の最小画面
- スマホブラウザからの写真アップロード画面
- 観察記録の全件表示と検索
- 解析結果の再解析と手動修正
- 植物DBと画像のzipバックアップ
- Discord Webhook通知の下準備

## ドキュメント

- 仕様書: `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\docs\SPECIFICATION.md`
- 実装計画書: `C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\docs\IMPLEMENTATION_PLAN.md`

## 初期方針

- Androidアプリは OPPO Reno11 A / ColorOS 15 / Android 15 を初期対象にする
- PC側は Windows 11 Pro で FastAPI + SQLite + Gemini CLI を動かす
- 外出先からの送信は Cloudflare Tunnel 経由を想定する
- Discordは主処理ではなく、解析完了通知として使う

## PCサーバーの起動

PowerShellで以下を実行します。

```powershell
cd C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex
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
```

## 画像3枚のテスト送信

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

アップロード画面では、既存写真を選ぶ場合は `写真から選ぶ`、その場で撮る場合は `カメラで撮る` を使います。

## バックアップ

Web画面の `保存` からAPIキーを入力し、`zipを作成してダウンロード` を押します。

zipには以下が入ります。

- `plants.sqlite`
- `images/`
- `manifest.json`

作成したzipは以下にも残ります。

```text
C:\Users\sgmxk\Desktop\AI\repos\github\harunamitrader\plant-dex\data\exports
```

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
```

サーバーを再起動します。

```powershell
uvicorn server.app.main:app --reload
```

その後、もう一度画像3枚を送信します。Gemini CLIには次の形式でプロンプトを渡します。

```text
gemini --output-format text -p "<画像3枚のパスを含む植物判定プロンプト>"
```

Geminiの出力がJSONとして解釈できれば、図鑑ページに実際の植物名と解析JSONが保存されます。
