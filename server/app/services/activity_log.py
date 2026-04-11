from datetime import datetime

from ..config import LOG_DIR


def write_log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    line = f"{timestamp} {message}\n"
    with (LOG_DIR / "server.log").open("a", encoding="utf-8") as file:
        file.write(line)
