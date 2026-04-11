import json
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .config import IMAGE_DIR, PROJECT_DIR, ensure_data_dirs, get_settings
from .services.discord_notify import notify_analysis_finished
from .services.gemini_cli import analyze_images
from .services.image_store import save_observation_images

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


@app.get("/observations/{observation_id}", response_class=HTMLResponse)
def observation_detail(request: Request, observation_id: str) -> HTMLResponse:
    observation = db.get_observation(observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="観察記録が見つかりません。")
    return templates.TemplateResponse(
        "observation_detail.html",
        {"request": request, "observation": present_observation(observation)},
    )


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
        db.set_observation_status(observation_id, "analyzing")
        result = analyze_images(image_paths)
        result_path = image_paths[0].parent / "result.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        plant_id = db.save_analysis_result(observation_id, result)
        plant = db.get_plant(plant_id)
        if plant:
            notify_analysis_finished(
                plant["display_name"],
                result.get("confidence"),
                f"{get_settings().base_url}/observations/{observation_id}",
            )
    except Exception as exc:
        db.set_observation_status(observation_id, "analysis_failed", str(exc))


def present_plant(row) -> dict:
    item = dict(row)
    item["representative_image_url"] = media_url(item.get("representative_image_path"))
    return item


def present_observation(row) -> dict:
    item = dict(row)
    item["image_urls"] = [
        media_url(item.get("image1_path")),
        media_url(item.get("image2_path")),
        media_url(item.get("image3_path")),
    ]
    return item


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
