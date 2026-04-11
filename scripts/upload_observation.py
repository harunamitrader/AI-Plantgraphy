import argparse
from pathlib import Path

import requests


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload three plant photos to Plant Dex.")
    parser.add_argument("images", nargs=3, help="Three image file paths.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/observations")
    parser.add_argument("--api-key", default="change-me")
    parser.add_argument("--note", default="")
    parser.add_argument("--location-label", default="")
    args = parser.parse_args()

    image_paths = [Path(path) for path in args.images]
    for path in image_paths:
        if not path.exists():
            raise SystemExit(f"Image not found: {path}")

    opened_files = []
    try:
        files = []
        for path in image_paths:
            handle = path.open("rb")
            opened_files.append(handle)
            files.append(("images", (path.name, handle, content_type(path))))

        response = requests.post(
            args.url,
            headers={"X-Plant-Dex-Api-Key": args.api_key},
            files=files,
            data={
                "note": args.note,
                "location_label": args.location_label,
            },
            timeout=120,
        )
        print(f"status_code={response.status_code}")
        print(response.text)
        response.raise_for_status()
    finally:
        for handle in opened_files:
            handle.close()


def content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"


if __name__ == "__main__":
    main()

