import json
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .config import IMAGE_DIR, PROJECT_DIR, ensure_data_dirs, get_settings
from .services.activity_log import write_log
from .services.connectivity import build_connectivity
from .services.discord_notify import notify_analysis_failed, notify_analysis_finished
from .services.export_store import create_export_zip
from .services.gemini_cli import analyze_images, normalize_confidence, normalize_result
from .services.image_store import save_observation_images
from .services.observation_cleanup import remove_observation_images
from .services.qr_code import qr_data_url

ensure_data_dirs()

app = FastAPI(title="Plant Dex", version="0.1.0")
templates = Jinja2Templates(directory=Path(__file__).parent / "web" / "templates")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "web" / "static"), name="static")
app.mount("/media", StaticFiles(directory=IMAGE_DIR), name="media")


@app.on_event("startup")
def startup() -> None:
    db.init_db()


def require_api_key(x_plant_dex_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_plant_dex_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="APIキーが正しくありません。")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/connectivity")
def connectivity() -> dict:
    return build_connectivity()


@app.post("/api/observations", dependencies=[Depends(require_api_key)])
async def create_observation(
    background_tasks: BackgroundTasks,
    images: list[UploadFile] = File(...),
    captured_at: str | None = Form(default=None),
    note: str | None = Form(default=None),
    location_label: str | None = Form(default=None),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
) -> dict:
    observation_id, image_paths = await save_observation_images(images)
    write_log(f"observation_received id={observation_id}")
    db.create_observation(
        observation_id=observation_id,
        image_paths=image_paths,
        captured_at=captured_at,
        note=note,
        location_label=location_label,
        latitude=latitude,
        longitude=longitude,
    )
    background_tasks.add_task(run_analysis, observation_id, image_paths)
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
    return dict(observation)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "plants": [present_plant(row) for row in db.list_plants()],
            "recent_observations": [present_observation(row) for row in db.list_recent_observations()],
        },
    )


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/connect", response_class=HTMLResponse)
def connect_page(request: Request) -> HTMLResponse:
    info = build_connectivity()
    primary_upload_url = first_url(info["upload_urls"]["tailscale"]) or first_url(info["upload_urls"]["local"])
    primary_home_url = first_url(info["tailscale_urls"]) or first_url(info["local_urls"])
    return templates.TemplateResponse(
        "connect.html",
        {
            "request": request,
            "connectivity": info,
            "primary_upload_url": primary_upload_url,
            "primary_home_url": primary_home_url,
            "upload_qr": qr_data_url(primary_upload_url) if primary_upload_url else "",
            "home_qr": qr_data_url(primary_home_url) if primary_home_url else "",
        },
    )


@app.get("/export", response_class=HTMLResponse)
def export_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("export.html", {"request": request})


@app.post("/api/export", dependencies=[Depends(require_api_key)])
def export_data() -> FileResponse:
    export_path = create_export_zip()
    write_log(f"export_created path={export_path}")
    return FileResponse(
        export_path,
        media_type="application/zip",
        filename=export_path.name,
    )


@app.get("/plants/{plant_id}", response_class=HTMLResponse)
def plant_detail(request: Request, plant_id: str) -> HTMLResponse:
    plant = db.get_plant(plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail="植物が見つかりません。")
    return templates.TemplateResponse(
        "plant_detail.html",
        {
            "request": request,
            "plant": present_plant(plant),
            "observations": [present_observation(row) for row in db.list_observations_for_plant(plant_id)],
        },
    )


@app.get("/observations", response_class=HTMLResponse)
def observations(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "observations.html",
        {
            "request": request,
            "observations": [present_observation(row) for row in db.list_observations()],
        },
    )


@app.get("/observations/{observation_id}", response_class=HTMLResponse)
def observation_detail(request: Request, observation_id: str) -> HTMLResponse:
    observation = db.get_observation(observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="観察記録が見つかりません。")
    return templates.TemplateResponse(
        "observation_detail.html",
        {"request": request, "observation": present_observation(observation)},
    )


@app.post("/api/observations/{observation_id}/reanalyze", dependencies=[Depends(require_api_key)])
def reanalyze(observation_id: str, background_tasks: BackgroundTasks) -> dict:
    observation = db.get_observation(observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="観察記録が見つかりません。")

    image_paths = [
        Path(observation["image1_path"]),
        Path(observation["image2_path"]),
        Path(observation["image3_path"]),
    ]
    db.set_observation_status(observation_id, "queued")
    background_tasks.add_task(run_analysis, observation_id, image_paths)
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
        "review.html",
        {
            "request": request,
            "observations": [present_observation(row) for row in db.list_review_observations()],
        },
    )


def run_analysis(observation_id: str, image_paths: list[Path]) -> None:
    try:
        write_log(f"analysis_started id={observation_id}")
        db.set_observation_status(observation_id, "analyzing")
        result = analyze_images(image_paths)
        result_path = image_paths[0].parent / "result.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        plant_id = db.save_analysis_result(observation_id, result)
        plant = db.get_plant(plant_id)
        write_log(f"analysis_finished id={observation_id} plant_id={plant_id}")
        if plant:
            notify_analysis_finished(
                plant["display_name"],
                result.get("confidence"),
                f"{get_settings().base_url}/observations/{observation_id}",
            )
    except Exception as exc:
        message = str(exc)
        db.set_observation_status(observation_id, "analysis_failed", message)
        write_log(f"analysis_failed id={observation_id} error={message[:500]}")
        notify_analysis_failed(
            observation_id,
            message,
            f"{get_settings().base_url}/observations/{observation_id}",
        )


def present_plant(row) -> dict:
    item = dict(row)
    item["representative_image_url"] = media_url(item.get("representative_image_path"))
    item["last_seen_label"] = short_date(item.get("last_observed_at"))
    return item


def present_observation(row) -> dict:
    item = dict(row)
    item["image_urls"] = [
        media_url(item.get("image1_path")),
        media_url(item.get("image2_path")),
        media_url(item.get("image3_path")),
    ]
    item["analysis"] = parse_analysis(item.get("raw_result_json"))
    item["analysis"]["basic_profile_display"] = profile_text(item["analysis"], "basic")
    item["analysis"]["visual_appeal_display"] = profile_text(item["analysis"], "visual")
    item["display_name"] = item["analysis"].get("common_name_ja") or item.get("plant_name") or "解析待ち"
    item["confidence_percent"] = percent_label(item.get("confidence") or item["analysis"].get("confidence"))
    item["status_label"] = status_label(item.get("status"))
    item["observed_label"] = short_date(item.get("captured_at") or item.get("received_at"))
    return item


def parse_analysis(raw_json: str | None) -> dict:
    if not raw_json:
        return {}
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return normalize_result(value) if isinstance(value, dict) else {}


def profile_text(analysis: dict, kind: str) -> str:
    if kind == "visual":
        text = analysis.get("visual_appeal_text")
        fallback = "見た目の特徴と魅力はまだありません。"
    else:
        text = analysis.get("basic_profile_text") or analysis.get("plant_profile_text")
        fallback = "基本的な特徴はまだありません。"

    if isinstance(text, str) and text.strip():
        if "未生成です" in text:
            return fallback
        return text.strip()

    legacy_profile = analysis.get("plant_profile")
    if kind == "basic" and isinstance(legacy_profile, dict):
        overview = legacy_profile.get("overview")
        if isinstance(overview, str) and overview.strip():
            return overview.strip()

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
        try:
            relative = path.relative_to(PROJECT_DIR)
        except ValueError:
            return ""
    return "/media/" + "/".join(relative.parts)


def first_url(values: list[str]) -> str:
    return values[0] if values else ""
