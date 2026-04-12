# Windowsクイックスタート

Plant DexをWindows PCで動かし、スマホからTailscale経由で使うための最短手順です。

## 1. 必要なもの

- Windows 11
- Python 3.12以上
- Gemini CLI
- Tailscaleアカウント
- AndroidまたはiPhoneのスマホ

## 2. ダウンロード

GitHubからzipをダウンロードして展開するか、Gitを使う場合は以下を実行します。

```powershell
git clone https://github.com/harunamitrader/plant-dex.git
cd plant-dex
```

## 3. 初期セットアップ

PowerShellで以下を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
```

この処理で以下を行います。

- Python仮想環境 `.venv` を作成
- 必要なPythonパッケージをインストール
- `.env` を作成
- APIキーをランダムな値に変更

## 4. 起動ショートカットを作る

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_desktop_shortcut.ps1
```

デスクトップに `Plant Dex を起動` が作成されます。

## 5. Plant Dexを起動

デスクトップの `Plant Dex を起動` を開きます。

PCのブラウザで接続ページが開きます。

```text
http://127.0.0.1:8000/connect
```

## 6. Tailscaleを準備

1. PCにTailscaleをインストールします。
2. スマホにもTailscaleをインストールします。
3. PCとスマホで同じTailscaleアカウントにログインします。
4. スマホ側のTailscaleをONにします。

## 7. スマホから開く

PCの接続ページに表示されるQRコードをスマホで読みます。

写真を送る場合は `写真を送る` のQRコードを使います。

## 8. Gemini CLIを有効にする

PowerShellで以下が動くことを確認します。

```powershell
gemini --version
```

`.env` を開いて以下に変更します。

```text
PLANT_DEX_GEMINI_ENABLED=true
PLANT_DEX_GEMINI_COMMAND=gemini
```

Plant Dexを再起動します。

## 9. 困ったとき

診断ページを開きます。

```text
http://127.0.0.1:8000/diagnostics
```

接続、保存先、Gemini CLI、APIキーの状態を確認できます。

## 10. テスト

開発者向けの確認は以下で実行します。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```
