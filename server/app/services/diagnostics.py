from pathlib import Path

from .. import db
from ..config import DB_PATH, EXPORT_DIR, IMAGE_DIR, LOG_DIR, get_settings
from .connectivity import build_connectivity


def build_diagnostics() -> dict:
    settings = get_settings()
    connectivity = build_connectivity()
    checks = [
        check_item(
            "api_key",
            "APIキー",
            connectivity["checks"]["api_key"] == "set",
            "初期値のままです。`.env` の `PLANT_DEX_API_KEY` を変更してください。",
        ),
        check_item(
            "gemini_cli",
            "Gemini CLI",
            connectivity["checks"]["gemini_cli"] == "ok",
            "Gemini CLIが見つかりません。`gemini --version` が動く状態にしてください。",
            skipped=not settings.gemini_enabled,
            skipped_message="Gemini解析は無効です。仮解析で使う場合はこのままで大丈夫です。",
        ),
        check_item(
            "tailscale",
            "Tailscale接続",
            connectivity["checks"]["tailscale_ip"] == "found",
            "Tailscale IPが見つかりません。PCのTailscaleをONにしてください。",
        ),
        path_check("image_dir", "画像保存先", IMAGE_DIR, directory=True),
        path_check("log_dir", "ログ保存先", LOG_DIR, directory=True),
        path_check("export_dir", "バックアップ保存先", EXPORT_DIR, directory=True),
        path_check("database", "データベース", DB_PATH, directory=False),
    ]

    try:
        plants_count = len(db.list_plants())
        observations_count = len(db.list_observations())
    except Exception:
        plants_count = None
        observations_count = None

    return {
        "ok": all(item["status"] in {"ok", "skipped"} for item in checks),
        "checks": checks,
        "counts": {
            "plants": plants_count,
            "observations": observations_count,
        },
        "connectivity": connectivity,
        "settings": {
            "base_url": settings.base_url,
            "gemini_enabled": settings.gemini_enabled,
            "gemini_timeout_seconds": settings.gemini_timeout_seconds,
            "discord_enabled": bool(settings.discord_webhook_url.strip()),
        },
    }


def check_item(
    key: str,
    label: str,
    passed: bool,
    message: str,
    skipped: bool = False,
    skipped_message: str = "",
) -> dict:
    if skipped:
        return {
            "key": key,
            "label": label,
            "status": "skipped",
            "message": skipped_message,
        }
    return {
        "key": key,
        "label": label,
        "status": "ok" if passed else "error",
        "message": "OK" if passed else message,
    }


def path_check(key: str, label: str, path: Path, directory: bool) -> dict:
    try:
        if directory:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                db.init_db()
            with path.open("ab"):
                pass
    except OSError as exc:
        return {
            "key": key,
            "label": label,
            "status": "error",
            "message": f"{path} に書き込めません: {exc}",
        }

    return {
        "key": key,
        "label": label,
        "status": "ok",
        "message": str(path),
    }
