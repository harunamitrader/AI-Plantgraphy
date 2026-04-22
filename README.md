# AI Plantgraphy

![AI Plantgraphy](docs/assets/ai-plantgraphy-header.jpg)

AI Plantgraphy は、スマホで撮った植物写真をAIで解析し、自分だけの植物図鑑を作るWebアプリです。
庭木、草花、鉢植え、公園で見つけた植物などを写真と名前、特徴、手入れメモ付きで残せます。

## できること

- スマホで植物の写真を1〜3枚選んで送信
- 自宅PC上の Gemini CLI で植物名を推定
- 解析結果、候補、特徴、見た目の魅力、手入れメモを保存
- 同じ種類の植物をまとめて図鑑化
- スマホから図鑑・観察記録・確認待ちを閲覧
- Tailscaleを使って外出先から自宅PCへ安全に接続
- 写真を軽量化して、スマホ表示を重くしすぎない
- zipバックアップ、場所ラベル、Geminiモデル選択に対応

## こんな人向け

- 庭やベランダの植物を写真付きで整理したい
- 植物名をAIに調べさせつつ、自分の記録として残したい
- なるべくクラウドに写真を預けず、自宅PC中心で使いたい
- スマホアプリのように使える個人用Webアプリを試したい

## 必要なもの

- Windows 11 PC
- AndroidまたはiPhoneのスマホ
- Gemini CLI
- Tailscaleアカウント
- GitとPython 3.11以上

初期確認は Windows 11 Pro、OPPO Reno11 A、ColorOS 15 / Android 15 を中心に行っています。

## まず使う

PowerShellでリポジトリを取得して、セットアップします。

```powershell
git clone https://github.com/harunamitrader/AI-Plantgraphy.git
cd AI-Plantgraphy
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\create_desktop_shortcut.ps1
```

デスクトップに `AI Plantgraphy を起動` が作成されます。
それを開くと、PCサーバーとブラウザが立ち上がります。

詳しい手順:

- Windowsクイックスタート: [docs/QUICK_START_WINDOWS.md](docs/QUICK_START_WINDOWS.md)
- Tailscaleセットアップ: [docs/TAILSCALE_SETUP.md](docs/TAILSCALE_SETUP.md)

## Gemini CLIを有効にする

まずPCでGemini CLIが使えることを確認します。

```powershell
gemini --version
gemini --help
```

`.env` を開いて、以下を設定します。

```text
PLANT_DEX_GEMINI_ENABLED=true
PLANT_DEX_GEMINI_COMMAND=gemini
PLANT_DEX_GEMINI_MODEL=gemini-3-flash-preview
```

環境変数名は、旧名称との互換性のため `PLANT_DEX_` のまま残しています。
アプリ名は AI Plantgraphy です。

## スマホから使う

外出先で使う場合は、PCとスマホの両方でTailscaleにログインします。
PC側の設定ページに表示されるURLまたはQRコードをスマホで開いてください。

連続カメラを外出先で使うには、Tailscale ServeのHTTPS URLが必要です。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure_tailscale_https.ps1
```

HTTPS化が難しい場合でも、通常カメラと写真選択は使えます。

## 写真を送る

Web画面では、次の3つの方法で写真候補を作れます。

- 連続カメラ
- 通常カメラ
- 写真から選ぶ

候補が3枚以上ある場合は、解析に使う写真を選べます。
何も選ばない場合は、あとから追加した3枚が優先されます。
1枚または2枚でも送信できます。

## データの保存場所

写真、SQLite DB、ログ、バックアップはPC内の `data` フォルダに保存されます。
GitHubへ公開するときは `data` と `.env` を含めないでください。

## バックアップ

Web画面の `設定` から、画像とデータベースをzipで保存できます。
作成したzipは以下にも残ります。

```text
data\exports
```

## テスト

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s .\server\tests -p "test_*.py"
.\.venv\Scripts\python.exe -m compileall .\server .\scripts
```

## ドキュメント

- 仕様書: [docs/SPECIFICATION.md](docs/SPECIFICATION.md)
- 実装計画書: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
- Windowsクイックスタート: [docs/QUICK_START_WINDOWS.md](docs/QUICK_START_WINDOWS.md)
- Tailscaleセットアップ: [docs/TAILSCALE_SETUP.md](docs/TAILSCALE_SETUP.md)
- 変更履歴: [CHANGELOG.md](CHANGELOG.md)
- 貢献ガイド: [CONTRIBUTING.md](CONTRIBUTING.md)
- セキュリティ: [SECURITY.md](SECURITY.md)

## 注意

AIの植物判定は間違うことがあります。
食用・薬用・毒性判断など、安全に関わる用途ではAI結果だけを信じないでください。

APIキー、Discord Webhook URL、位置情報、個人写真を公開IssueやPull Requestに貼らないでください。

## ライセンス

MIT Licenseです。詳細は [LICENSE](LICENSE) を確認してください。
