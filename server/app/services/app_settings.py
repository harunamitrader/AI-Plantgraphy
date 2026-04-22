import json

from .. import config


DEFAULT_LOCATION_LABELS = ["庭", "玄関前", "ベランダ", "鉢植え", "公園", "その他"]


def settings_path():
    return config.DATA_DIR / "settings.json"


def load_settings() -> dict:
    path = settings_path()
    if not path.exists():
        return {"location_labels": DEFAULT_LOCATION_LABELS}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"location_labels": DEFAULT_LOCATION_LABELS}
    if not isinstance(data, dict):
        return {"location_labels": DEFAULT_LOCATION_LABELS}
    labels = data.get("location_labels")
    if not isinstance(labels, list):
        labels = DEFAULT_LOCATION_LABELS
    return {"location_labels": normalize_labels(labels)}


def save_settings(data: dict) -> None:
    config.ensure_data_dirs()
    settings_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_location_labels() -> list[str]:
    return load_settings()["location_labels"]


def add_location_label(label: str) -> list[str]:
    labels = get_location_labels()
    cleaned = clean_label(label)
    if cleaned and cleaned not in labels:
        labels.append(cleaned)
        save_settings({"location_labels": labels})
    return labels


def remove_location_label(label: str) -> list[str]:
    cleaned = clean_label(label)
    labels = [item for item in get_location_labels() if item != cleaned]
    save_settings({"location_labels": labels})
    return labels


def normalize_labels(values: list[object]) -> list[str]:
    labels: list[str] = []
    for value in values:
        label = clean_label(str(value))
        if label and label not in labels:
            labels.append(label)
    return labels or DEFAULT_LOCATION_LABELS


def clean_label(value: str) -> str:
    return value.strip()[:40]
