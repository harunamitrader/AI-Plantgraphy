import requests

from ..config import get_settings


def notify_analysis_finished(display_name: str, confidence: float | None, detail_url: str) -> None:
    settings = get_settings()
    if not settings.discord_webhook_url:
        return

    confidence_text = "不明" if confidence is None else f"{confidence:.0%}"
    requests.post(
        settings.discord_webhook_url,
        json={
            "content": (
                "新しい植物を解析しました\n"
                f"推定: {display_name}\n"
                f"信頼度: {confidence_text}\n"
                f"詳細: {detail_url}"
            )
        },
        timeout=10,
    )

