import json
import ipaddress
import socket
import subprocess

from ..config import get_settings

DEFAULT_PORT = 8000


def build_connectivity(port: int = DEFAULT_PORT) -> dict:
    settings = get_settings()
    local_ips = list_local_ipv4_addresses()
    local_urls = [base_url(ip, port) for ip in local_ips if is_private_lan_ip(ip)]
    tailscale_urls = [base_url(ip, port) for ip in local_ips if is_tailscale_ip(ip)]
    tailscale_status = get_tailscale_status()
    tailscale_https_urls = tailscale_https_urls_from_status(tailscale_status)
    tailscale_serve_status = check_tailscale_serve()
    gemini_status = check_gemini_cli(settings.gemini_command)
    api_key_status = "default" if settings.api_key == "change-me" else "set"

    return {
        "server": {
            "port": port,
            "base_url": settings.base_url,
        },
        "local_urls": local_urls,
        "tailscale_urls": tailscale_urls,
        "tailscale_https_urls": tailscale_https_urls,
        "upload_urls": {
            "local": [f"{url}upload" for url in local_urls],
            "tailscale": [f"{url}upload" for url in tailscale_urls],
            "tailscale_https": [f"{url}upload" for url in tailscale_https_urls],
        },
        "checks": {
            "gemini_cli": gemini_status,
            "api_key": api_key_status,
            "tailscale_cli": "ok" if tailscale_status else "not_found",
            "tailscale_serve": tailscale_serve_status,
            "tailscale_https": "found" if tailscale_https_urls else "not_found",
            "tailscale_ip": "found" if tailscale_urls else "not_found",
            "local_ip": "found" if local_urls else "not_found",
        },
    }


def get_tailscale_status() -> dict | None:
    try:
        completed = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        status = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return None
    return status if isinstance(status, dict) else None


def tailscale_https_urls_from_status(status: dict | None) -> list[str]:
    if not status:
        return []
    self_info = status.get("Self") or {}
    dns_name = str(self_info.get("DNSName") or "").strip().rstrip(".")
    if not dns_name:
        return []
    return [f"https://{dns_name}/"]


def check_tailscale_serve() -> str:
    try:
        completed = subprocess.run(
            ["tailscale", "serve", "status", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "not_found"
    if completed.returncode != 0:
        return "error"
    try:
        status = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return "unknown"
    return "configured" if status else "not_configured"


def list_local_ipv4_addresses() -> list[str]:
    addresses = set()
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addresses.add(item[4][0])
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            addresses.add(probe.getsockname()[0])
    except OSError:
        pass

    return sorted(ip for ip in addresses if not ip.startswith("127."))


def is_private_lan_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.is_private and not is_tailscale_ip(value)


def is_tailscale_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip in ipaddress.ip_network("100.64.0.0/10")


def base_url(ip: str, port: int) -> str:
    return f"http://{ip}:{port}/"


def check_gemini_cli(command: str) -> str:
    executable = command.split()[0] if command.strip() else "gemini"
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "not_found"
    return "ok" if completed.returncode == 0 else "error"
