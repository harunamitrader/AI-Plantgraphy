import json
import time
from pathlib import Path
from threading import Lock

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .config import IMAGE_DIR, PROJECT_DIR, ensure_data_dirs, gemini_model_choices, get_settings
from .services.activity_log import write_log
from .services.app_settings import add_location_label, get_location_labels, remove_location_label
from .services.connectivity import build_connectivity
from .services.discord_notify import notify_analysis_failed, notify_analysis_finished
from .services.export_store import create_export_zip
from .services.gemini_cli import analyze_images, normalize_confidence, normalize_result
from .services.image_store import save_observation_images
from .services.diagnostics import build_diagnostics
from .services.observation_cleanup import remove_observation_images
from .services.qr_code import qr_data_url

ensure_data_dirs()

app = FastAPI(title="AI Plantgraphy", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_origin_regex=r"^https://[a-z0-9-]+\.github\.io$|^http://localhost:\d+$|^http://127\.0\.0\.1:\d+$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory=Path(__file__).parent / "web" / "templates")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "web" / "static"), name="static")
app.mount("/media", StaticFiles(directory=IMAGE_DIR), name="media")

ANALYSIS_PROGRESS: dict[str, dict] = {}
ANALYSIS_PROGRESS_LOCK = Lock()


@app.on_event("startup")
def startup() -> None:
    db.init_db()


def require_api_key(x_plant_dex_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_plant_dex_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="パスワードが正しくありません。")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/bootstrap")
def bootstrap() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "app_name": "AI Plantgraphy",
        "server_name": settings.server_name,
        "server_id": settings.server_name.lower(),
        "base_url": settings.base_url,
        "gemini_enabled": settings.gemini_enabled,
        "gemini_model": settings.gemini_model,
        "gemini_model_choices": gemini_model_choices(),
        "location_labels": get_location_labels(),
    }


@app.get("/api/connectivity")
def connectivity() -> dict:
    return build_connectivity()


@app.get("/api/diagnostics")
def diagnostics() -> dict:
    return build_diagnostics()


@app.post("/api/observations", dependencies=[Depends(require_api_key)])
async def create_observation(
    background_tasks: BackgroundTasks,
    images: list[UploadFile] = File(...),
    gemini_model: str | None = Form(default=None),
    captured_at: str | None = Form(default=None),
    note: str | None = Form(default=None),
    location_label: str | None = Form(default=None),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
) -> dict:
    save_started_at = time.perf_counter()
    observation_id, image_paths = await save_observation_images(images)
    save_seconds = elapsed_seconds(save_started_at)
    write_log(f"observation_received id={observation_id} save_seconds={save_seconds}")
    set_analysis_progress(observation_id, "queued", "解析待ち", 0)
    db.create_observation(
        observation_id=observation_id,
        image_paths=image_paths,
        captured_at=captured_at,
        note=note,
        location_label=location_label,
        latitude=latitude,
        longitude=longitude,
    )
    background_tasks.add_task(run_analysis, observation_id, image_paths, gemini_model)
    return {
        "observation_id": observation_id,
        "status": "queued",
        "detail_url": f"/observations/{observation_id}",
    }


@app.get("/api/observations/{observation_id}")
def api_observation(observation_id: str) -> dict:
    observation = db.get_observation(observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="観察記録が見つかりません。")
    data = present_observation(observation)
    data["analysis_progress"] = get_analysis_progress(observation_id, data.get("status"))
    return data


@app.get("/api/plants")
def api_plants() -> dict:
    return {
        "plants": [present_plant(row) for row in db.list_plants()],
    }


@app.get("/api/plants/{plant_id}")
def api_plant_detail(plant_id: str) -> dict:
    plant = db.get_plant(plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail="植物が見つかりません。")
    return {
        "plant": present_plant(plant),
        "observations": [present_observation(row) for row in db.list_observations_for_plant(plant_id)],
        "photo_urls": [media_url(path) for path in db.list_recent_image_paths_for_plant(plant_id)],
    }


@app.get("/api/observations")
def api_observations() -> dict:
    return {
        "observations": [present_observation(row) for row in db.list_observations()],
    }


@app.get("/api/review")
def api_review() -> dict:
    return {
        "observations": [present_observation(row) for row in db.list_review_observations()],
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    recent_observations = [present_observation(row) for row in db.list_recent_observations()]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "plants": [present_plant(row) for row in db.list_plants()],
            "recent_observations": recent_observations,
            "review_count": sum(
                1
                for observation in recent_observations
                if observation.get("status") in {"needs_review", "analysis_failed", "queued", "analyzing"}
            ),
        },
    )


@app.get("/plants", response_class=HTMLResponse)
def plant_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "plants.html",
        {
            "plants": [present_plant(row) for row in db.list_plants()],
        },
    )


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "gemini_model": settings.gemini_model,
            "gemini_model_choices": gemini_model_choices(),
            "location_labels": get_location_labels(),
        },
    )


@app.get("/pending-local", response_class=HTMLResponse)
def pending_local_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "pending_local.html",
        {},
    )


@app.get("/connect", response_class=HTMLResponse)
def connect_page() -> RedirectResponse:
    return RedirectResponse("/settings", status_code=307)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    info = build_connectivity()
    diagnostics = build_diagnostics()
    settings = get_settings()
    tailscale_https_is_ready = info["checks"]["tailscale_serve"] == "configured"
    primary_upload_url = (
        (first_url(info["upload_urls"]["tailscale_https"]) if tailscale_https_is_ready else None)
        or first_url(info["upload_urls"]["tailscale"])
        or first_url(info["upload_urls"]["local"])
    )
    shared_frontend_url = settings.shared_frontend_url.strip()
    input_api_url = (
        first_url(info["tailscale_https_urls"])
        or first_url(info["tailscale_urls"])
        or first_url(info["local_urls"])
    )
    primary_home_url = shared_frontend_url or input_api_url
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "connectivity": info,
            "diagnostics": diagnostics,
            "shared_frontend_url": shared_frontend_url,
            "input_api_url": input_api_url,
            "primary_upload_url": primary_upload_url,
            "primary_home_url": primary_home_url,
            "upload_qr": qr_data_url(primary_upload_url) if primary_upload_url else "",
            "home_qr": qr_data_url(primary_home_url) if primary_home_url else "",
            "gemini_model": settings.gemini_model,
            "gemini_model_choices": gemini_model_choices(),
            "location_labels": get_location_labels(),
        },
    )


@app.get("/diagnostics", response_class=HTMLResponse)
def diagnostics_page() -> RedirectResponse:
    return RedirectResponse("/settings", status_code=307)


@app.get("/export", response_class=HTMLResponse)
def export_page() -> RedirectResponse:
    return RedirectResponse("/settings", status_code=307)


@app.post("/api/export", dependencies=[Depends(require_api_key)])
def export_data() -> FileResponse:
    export_path = create_export_zip()
    write_log(f"export_created path={export_path}")
    return FileResponse(
        export_path,
        media_type="application/zip",
        filename=export_path.name,
    )


@app.get("/api/settings/location-labels")
def api_location_labels() -> dict:
    return {"location_labels": get_location_labels()}


@app.post("/api/settings/location-labels", dependencies=[Depends(require_api_key)])
def api_add_location_label(label: str = Form(default="")) -> dict:
    cleaned = label.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="場所ラベルを入力してください。")
    labels = add_location_label(cleaned)
    write_log(f"location_label_added label={cleaned}")
    return {"location_labels": labels}


@app.delete("/api/settings/location-labels/{label}", dependencies=[Depends(require_api_key)])
def api_remove_location_label(label: str) -> dict:
    labels = remove_location_label(label)
    write_log(f"location_label_removed label={label}")
    return {"location_labels": labels}


@app.get("/plants/{plant_id}", response_class=HTMLResponse)
def plant_detail(request: Request, plant_id: str) -> HTMLResponse:
    plant = db.get_plant(plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail="植物が見つかりません。")
    return templates.TemplateResponse(
        request,
        "plant_detail.html",
        {
            "plant": present_plant(plant),
            "observations": [present_observation(row) for row in db.list_observations_for_plant(plant_id)],
            "photo_urls": [media_url(path) for path in db.list_recent_image_paths_for_plant(plant_id)],
        },
    )


@app.get("/observations", response_class=HTMLResponse)
def observations(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "observations.html",
        {
            "observations": [present_observation(row) for row in db.list_observations()],
        },
    )


@app.get("/observations/{observation_id}", response_class=HTMLResponse)
def observation_detail(request: Request, observation_id: str) -> HTMLResponse:
    observation = db.get_observation(observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="観察記録が見つかりません。")
    return templates.TemplateResponse(
        request,
        "observation_detail.html",
        {
            "observation": present_observation(observation),
            "gemini_model": get_settings().gemini_model,
            "gemini_model_choices": gemini_model_choices(),
        },
    )


@app.post("/api/observations/{observation_id}/reanalyze", dependencies=[Depends(require_api_key)])
def reanalyze(
    observation_id: str,
    background_tasks: BackgroundTasks,
    gemini_model: str | None = Form(default=None),
) -> dict:
    observation = db.get_observation(observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="観察記録が見つかりません。")

    image_paths = [
        Path(path)
        for path in [
            observation["image1_path"],
            observation["image2_path"],
            observation["image3_path"],
        ]
        if path
    ]
    db.set_observation_status(observation_id, "queued")
    set_analysis_progress(observation_id, "queued", "解析待ち", 0)
    background_tasks.add_task(run_analysis, observation_id, image_paths, gemini_model)
    return {"status": "queued", "observation_id": observation_id}


@app.post("/api/observations/{observation_id}/correction", dependencies=[Depends(require_api_key)])
def correct_observation(
    observation_id: str,
    common_name_ja: str = Form(default=""),
    scientific_name: str | None = Form(default=None),
    note: str | None = Form(default=None),
    location_label: str | None = Form(default=None),
) -> dict:
    if not common_name_ja.strip() and not (scientific_name or "").strip():
        raise HTTPException(status_code=400, detail="植物名または学名を入力してください。")
    try:
        plant_id = db.apply_manual_correction(
            observation_id=observation_id,
            common_name_ja=common_name_ja,
            scientific_name=scientific_name,
            note=note,
            location_label=location_label,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="観察記録が見つかりません。") from None
    write_log(f"observation_corrected id={observation_id} plant_id={plant_id}")
    return {"status": "corrected", "observation_id": observation_id, "plant_id": plant_id}


@app.delete("/api/observations/{observation_id}", dependencies=[Depends(require_api_key)])
def delete_observation(observation_id: str) -> dict:
    observation = db.delete_observation(observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="観察記録が見つかりません。")
    remove_observation_images(observation["image1_path"])
    write_log(f"observation_deleted id={observation_id}")
    return {"status": "deleted", "observation_id": observation_id}


@app.get("/review", response_class=HTMLResponse)
def review(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "observations": [present_observation(row) for row in db.list_review_observations()],
        },
    )


def run_analysis(observation_id: str, image_paths: list[Path], gemini_model: str | None = None) -> None:
    analysis_started_at = time.perf_counter()
    try:
        model_label = gemini_model.strip() if gemini_model else ""
        write_log(f"analysis_started id={observation_id} model={model_label or 'default'}")
        db.set_observation_status(observation_id, "analyzing")
        set_analysis_progress(observation_id, "preparing", "画像準備中", 10)
        gemini_started_at = time.perf_counter()
        result = analyze_images(
            image_paths,
            gemini_model=gemini_model,
            progress_callback=lambda phase: set_analysis_phase(observation_id, phase),
            identity_callback=lambda identity: save_identity_preview(observation_id, identity),
        )
        gemini_total_seconds = elapsed_seconds(gemini_started_at)
        result.setdefault("analysis_timing", {})
        result["analysis_timing"]["server_gemini_total_seconds"] = gemini_total_seconds
        result_path = image_paths[0].parent / "result.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        set_analysis_progress(observation_id, "saving", "結果保存中", 92)
        db_started_at = time.perf_counter()
        plant_id = db.save_analysis_result(observation_id, result)
        db_seconds = elapsed_seconds(db_started_at)
        profile_seconds = 0.0
        if get_settings().gemini_enabled and db.plant_needs_profile(plant_id):
            set_analysis_progress(observation_id, "writing_profile", "図鑑解説作成中", 95)
            profile_started_at = time.perf_counter()
            try:
                profile = generate_plant_profile(
                    result.get("common_name_ja"),
                    result.get("scientific_name"),
                    gemini_model=gemini_model,
                )
                db.update_plant_profile(plant_id, profile)
            except Exception as exc:
                write_log(f"plant_profile_failed id={observation_id} plant_id={plant_id} error={str(exc)[:500]}")
            profile_seconds = elapsed_seconds(profile_started_at)
        total_seconds = elapsed_seconds(analysis_started_at)
        result["analysis_timing"]["db_save_seconds"] = db_seconds
        result["analysis_timing"]["plant_profile_seconds"] = profile_seconds
        result["analysis_timing"]["server_total_seconds"] = total_seconds
        db.update_observation_raw_result(observation_id, result)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        plant = db.get_plant(plant_id)
        write_log(
            f"analysis_finished id={observation_id} plant_id={plant_id} "
            f"total_seconds={total_seconds} gemini_seconds={gemini_total_seconds} db_seconds={db_seconds}"
        )
        set_analysis_progress(observation_id, "finished", "完了", 100)
        if plant:
            notify_analysis_finished(
                plant["display_name"],
                result.get("confidence"),
                f"{get_settings().base_url}/observations/{observation_id}",
            )
    except Exception as exc:
        total_seconds = elapsed_seconds(analysis_started_at)
        message = format_analysis_error(exc)
        db.set_observation_status(observation_id, "analysis_failed", message)
        set_analysis_progress(observation_id, "failed", "失敗", 100)
        write_log(f"analysis_failed id={observation_id} total_seconds={total_seconds} error={message[:500]}")
        notify_analysis_failed(
            observation_id,
            message,
            f"{get_settings().base_url}/observations/{observation_id}",
        )


def elapsed_seconds(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 3)


def set_analysis_phase(observation_id: str, phase: str) -> None:
    labels = {
        "identifying": ("identifying", "種類特定中", 35),
        "writing_profile": ("writing_profile", "図鑑解説作成中", 78),
    }
    status, label, percent = labels.get(phase, (phase, phase, 50))
    set_analysis_progress(observation_id, status, label, percent)


def save_identity_preview(observation_id: str, identity: dict) -> None:
    db.update_observation_identity_result(observation_id, identity)
    name = identity.get("common_name_ja") or identity.get("scientific_name") or "名称未確定"
    confidence = identity.get("confidence")
    set_analysis_progress(observation_id, "writing_profile", "解説文作成中", 78)
    write_log(f"analysis_identity_ready id={observation_id} name={name} confidence={confidence}")


def set_analysis_progress(observation_id: str, phase: str, label: str, percent: int) -> None:
    with ANALYSIS_PROGRESS_LOCK:
        ANALYSIS_PROGRESS[observation_id] = {
            "phase": phase,
            "label": label,
            "percent": percent,
            "updated_at": time.time(),
        }


def get_analysis_progress(observation_id: str, status: str | None) -> dict:
    with ANALYSIS_PROGRESS_LOCK:
        progress = dict(ANALYSIS_PROGRESS.get(observation_id) or {})
    if progress:
        return progress
    if status == "queued":
        return {"phase": "queued", "label": "解析待ち", "percent": 0}
    if status == "analyzing":
        return {"phase": "analyzing", "label": "解析中", "percent": 30}
    if status == "analysis_failed":
        return {"phase": "failed", "label": "失敗", "percent": 100}
    if status in {"analyzed", "needs_review"}:
        return {"phase": "finished", "label": "完了", "percent": 100}
    return {"phase": status or "unknown", "label": status or "不明", "percent": 0}


def format_analysis_error(exc: Exception) -> str:
    message = str(exc)
    if "timed out after" in message:
        return "Gemini CLIがタイムアウトしました。Gemini CLIのログイン状態、Gemini側のAPIキー、通信状態を確認してから再解析してください。"
    if len(message) > 600:
        return message[:597].rstrip() + "..."
    return message


def present_plant(row, absolute_urls: bool = False) -> dict:
    item = dict(row)
    item["representative_image_url"] = media_url(item.get("representative_image_path"))
    item["detail_url"] = f"/plants/{item['id']}"
    item["last_seen_label"] = short_date(item.get("last_observed_at"))
    item["basic_profile_display"] = clean_display_text(item.get("basic_profile_text"), "基本的な特徴はまだありません。")
    item["visual_appeal_display"] = clean_display_text(item.get("visual_appeal_text"), "見た目の特徴と魅力はまだありません。")
    item["care_notes_display"] = clean_display_text(item.get("care_notes"), "手入れメモはまだありません。")
    if absolute_urls:
        item["representative_image_url"] = absolute_public_url(item["representative_image_url"])
        item["detail_url"] = absolute_public_url(item["detail_url"])
    return item


def present_observation(row, absolute_urls: bool = False) -> dict:
    item = dict(row)
    item["image_urls"] = [
        media_url(path)
        for path in [
            item.get("image1_path"),
            item.get("image2_path"),
            item.get("image3_path"),
        ]
        if path
    ]
    item["analysis"] = parse_analysis(item.get("raw_result_json"))
    item["display_name"] = item["analysis"].get("common_name_ja") or item.get("plant_name") or "解析待ち"
    item["confidence_percent"] = percent_label(item.get("confidence") or item["analysis"].get("confidence"))
    item["status_label"] = status_label(item.get("status"))
    item["observed_label"] = short_date(item.get("captured_at") or item.get("received_at"))
    item["plant_url"] = f"/plants/{item.get('plant_id')}" if item.get("plant_id") else ""
    item["detail_url"] = f"/observations/{item['id']}"
    if absolute_urls:
        item["image_urls"] = [absolute_public_url(url) for url in item["image_urls"]]
        item["plant_url"] = absolute_public_url(item["plant_url"]) if item["plant_url"] else ""
        item["detail_url"] = absolute_public_url(item["detail_url"])
    return item


def parse_analysis(raw_json: str | None) -> dict:
    if not raw_json:
        return {}
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return normalize_result(value) if isinstance(value, dict) else {}


def clean_display_text(text: object, fallback: str) -> str:
    if isinstance(text, str) and text.strip():
        if "未生成です" in text:
            return fallback
        return text.strip()
    return fallback


def percent_label(value: object) -> str:
    if value is None:
        return "不明"
    return f"{normalize_confidence(value):.0%}"


def short_date(value: str | None) -> str:
    if not value:
        return "未入力"
    return value[:10]


def status_label(value: str | None) -> str:
    labels = {
        "queued": "待機中",
        "analyzing": "解析中",
        "analyzed": "解析済み",
        "needs_review": "確認待ち",
        "analysis_failed": "失敗",
    }
    return labels.get(value or "", value or "不明")


def media_url(path_value: str | None) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    try:
        relative = path.relative_to(IMAGE_DIR)
    except ValueError:
        parts = path.parts
        relative = None
        for index in range(len(parts) - 1):
            if parts[index].lower() == "images" and index > 0 and parts[index - 1].lower() == "data":
                relative = Path(*parts[index + 1 :])
                break
        if relative is None:
            try:
                relative = path.relative_to(PROJECT_DIR)
            except ValueError:
                return ""
    return "/media/" + "/".join(relative.parts)


def absolute_public_url(path: str | None) -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base_url = get_settings().base_url.rstrip("/")
    return f"{base_url}{path}" if base_url else path


def first_url(values: list[str]) -> str:
    return values[0] if values else ""
