"""FastAPI สำหรับแผนที่และพยากรณ์ PM2.5"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from thaiair.api import live
from thaiair.features.build import build_features
from thaiair.models import artifact

log = logging.getLogger(__name__)

INDEX_PATH = Path(__file__).with_name("index.html")
TIME_FEATURES = {"hour_sin", "hour_cos", "doy_sin", "doy_cos"}
LEVELS = (
    (15.0, "ดีมาก", "#58bcd5"),
    (25.0, "ดี", "#67c6a3"),
    (37.5, "ปานกลาง", "#f3d451"),
    (75.0, "เริ่มมีผลกระทบต่อสุขภาพ", "#f39b4a"),
    (float("inf"), "มีผลกระทบต่อสุขภาพ", "#e46666"),
)


def _model_path() -> Path:
    return Path(os.getenv("PM25_MODEL_PATH", str(artifact.DEFAULT_PATH)))


def _raw_path() -> Path:
    return Path(os.getenv("PM25_RAW_PATH", "data/raw/observations.parquet"))


def _stations_path() -> Path:
    return Path(os.getenv("PM25_STATIONS_PATH", "data/raw/stations.json"))


def _iso(value: Any) -> str:
    return pd.Timestamp(value).isoformat()


def air_quality(value: float) -> dict[str, str]:
    for limit, label, color in LEVELS:
        if value <= limit:
            return {"level": label, "color": color}
    raise AssertionError("LEVELS ต้องลงท้ายด้วย infinity")


class _State:
    artifact: dict[str, Any] | None = None
    raw: pd.DataFrame | None = None
    features: pd.DataFrame | None = None
    stations: list[dict[str, Any]] | None = None
    map_payload: dict[str, Any] | None = None
    source_status = "snapshot"
    refreshed_at: str | None = None
    refreshing = False
    refresh_task: asyncio.Task | None = None
    lock = Lock()

    @property
    def ready(self) -> bool:
        return all(
            value is not None
            for value in (self.artifact, self.raw, self.features, self.stations, self.map_payload)
        )


state = _State()


def _coverage(row: pd.Series, columns: list[str]) -> float:
    history_columns = [column for column in columns if column not in TIME_FEATURES]
    return float(row[history_columns].notna().mean()) if history_columns else 1.0


def _forecast(row: pd.DataFrame, horizon: int) -> tuple[float, str]:
    selected = artifact.forecaster(state.artifact, horizon)
    if selected["method"] == "persistence":
        return float(row["pm25"].iloc[0]), "persistence"
    features = row[state.artifact["feature_columns"]]
    value = float(selected["model"].predict(features)[0])
    return max(0.0, value), "model"


def _build_map_payload(now: datetime | None = None) -> dict[str, Any]:
    now_naive = pd.Timestamp(now or datetime.now(UTC)).tz_localize(None)
    latest = (
        state.features.sort_values(["station_id", "timestamp"])
        .groupby("station_id", sort=False)
        .tail(1)
        .set_index("station_id", drop=False)
    )
    horizons = artifact.horizons(state.artifact)
    stations = []

    for metadata in state.stations:
        station_id = metadata["station_id"]
        if station_id not in latest.index:
            continue
        row = latest.loc[[station_id]]
        based_on = pd.Timestamp(row["timestamp"].iloc[0])
        observed = row["pm25"].iloc[0]
        age_hours = max(0.0, (now_naive - based_on).total_seconds() / 3600)
        freshness = "fresh" if age_hours <= 3 else "stale" if age_hours <= 6 else "unavailable"
        coverage = _coverage(row.iloc[0], state.artifact["feature_columns"])
        available = pd.notna(observed) and freshness != "unavailable" and coverage >= 0.5

        observed_value = round(float(observed), 2) if pd.notna(observed) else None
        observed_quality = air_quality(observed_value) if observed_value is not None else {}
        forecasts = []
        for horizon in horizons:
            if available:
                value, method = _forecast(row, horizon)
                rounded = round(value, 2)
                forecasts.append(
                    {
                        "horizon_hours": horizon,
                        "predicted_for": _iso(based_on + pd.Timedelta(hours=horizon)),
                        "pm25": rounded,
                        "method": method,
                        **air_quality(rounded),
                    }
                )
            else:
                forecasts.append(
                    {
                        "horizon_hours": horizon,
                        "predicted_for": _iso(based_on + pd.Timedelta(hours=horizon)),
                        "pm25": None,
                        "method": "unavailable",
                        "level": "ข้อมูลไม่พอ",
                        "color": "#9aa7a5",
                    }
                )

        stations.append(
            {
                **metadata,
                "freshness": freshness,
                "feature_coverage": round(coverage, 2),
                "observed": {
                    "timestamp": _iso(based_on),
                    "pm25": observed_value,
                    **observed_quality,
                },
                "forecasts": forecasts,
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_status": state.source_status,
        "refreshed_at": state.refreshed_at,
        "available_horizons": [0, *horizons],
        "stations": stations,
    }


async def _refresh_forever(api_key: str) -> None:
    while True:
        state.refreshing = True
        try:
            raw, stations, success_count = await asyncio.to_thread(
                live.refresh,
                state.raw,
                state.stations,
                api_key=api_key,
            )
            features = build_features(raw, horizon=1)
            with state.lock:
                state.raw = raw
                state.features = features
                state.stations = stations
                state.source_status = "live"
                state.refreshed_at = datetime.now(UTC).isoformat(timespec="seconds")
                state.map_payload = _build_map_payload()
            log.info("live refresh สำเร็จ %d/%d สถานี", success_count, len(stations))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("live refresh ไม่สำเร็จ — ยังใช้ snapshot เดิม")
        finally:
            state.refreshing = False
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        state.artifact = artifact.load(_model_path())
        state.raw = pd.read_parquet(_raw_path())
        state.features = build_features(state.raw, horizon=1)
        state.stations = live.load_stations(_stations_path())
        state.source_status = "snapshot"
        state.refreshed_at = _iso(state.raw["timestamp"].max())
        state.map_payload = _build_map_payload()
        log.info("พร้อมเสิร์ฟ %d สถานี", len(state.map_payload["stations"]))

        api_key = os.getenv("OPENAQ_API_KEY", "").strip()
        if api_key:
            state.refresh_task = asyncio.create_task(_refresh_forever(api_key))
        else:
            log.warning("ไม่มี OPENAQ_API_KEY — เสิร์ฟ snapshot โดยไม่ refresh")
    except Exception:
        log.exception("โหลด production state ไม่สำเร็จ")

    yield

    if state.refresh_task:
        state.refresh_task.cancel()
        with suppress(asyncio.CancelledError):
            await state.refresh_task
    state.artifact = None
    state.raw = None
    state.features = None
    state.stations = None
    state.map_payload = None


app = FastAPI(title="ThaiAir — PM2.5 forecast", lifespan=lifespan)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,https://thaiair-web.vercel.app"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class PredictRequest(BaseModel):
    station_id: str = Field(examples=["oa:135:5077838"])
    timestamp: datetime | None = None
    horizon_hours: int = Field(default=24, examples=[3, 12, 24])


class PredictResponse(BaseModel):
    station_id: str
    based_on: datetime
    predicted_for: datetime
    pm25: float
    horizon_hours: int
    method: str
    feature_coverage: float
    level: str
    color: str
    model_trained_at: str


@app.get("/", include_in_schema=False)
def home() -> Response:
    web_app_url = os.getenv("WEB_APP_URL", "https://thaiair-web.vercel.app").strip()
    return RedirectResponse(web_app_url) if web_app_url else FileResponse(INDEX_PATH)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/ready")
def ready() -> dict[str, Any]:
    if not state.ready:
        raise HTTPException(status_code=503, detail="ยังโหลดโมเดลหรือข้อมูลไม่สำเร็จ")
    horizons = artifact.horizons(state.artifact)
    return {
        "status": "ready",
        "model_trained_at": state.artifact["trained_at"],
        "horizon_hours": max(horizons),
        "available_horizons": list(horizons),
        "history_rows": len(state.features),
        "source_status": state.source_status,
        "refreshed_at": state.refreshed_at,
        "refreshing": state.refreshing,
    }


@app.get("/stations")
def stations() -> dict[str, list[str]]:
    if not state.ready:
        raise HTTPException(status_code=503, detail="ยังโหลดโมเดลหรือข้อมูลไม่สำเร็จ")
    return {"stations": sorted(state.features["station_id"].unique())}


@app.get("/map-data")
def map_data() -> dict[str, Any]:
    if not state.ready:
        raise HTTPException(status_code=503, detail="ยังโหลดโมเดลหรือข้อมูลไม่สำเร็จ")
    with state.lock:
        payload = dict(state.map_payload)
    payload["refreshing"] = state.refreshing
    return payload


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    if not state.ready:
        raise HTTPException(status_code=503, detail="ยังโหลดโมเดลหรือข้อมูลไม่สำเร็จ")
    supported = artifact.horizons(state.artifact)
    if request.horizon_hours not in supported:
        raise HTTPException(
            status_code=422,
            detail=f"horizon_hours ต้องเป็นหนึ่งใน {list(supported)}",
        )

    rows = state.features[state.features["station_id"] == request.station_id]
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"ไม่รู้จักสถานี {request.station_id!r}")

    if request.timestamp is None:
        row = rows.iloc[[-1]]
    else:
        timestamp = pd.Timestamp(request.timestamp)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC").tz_localize(None)
        row = rows[rows["timestamp"] == timestamp]
        if row.empty:
            raise HTTPException(status_code=404, detail=f"ไม่มีข้อมูลที่เวลา {timestamp} UTC")

    coverage = _coverage(row.iloc[0], state.artifact["feature_columns"])
    if pd.isna(row["pm25"].iloc[0]) or coverage < 0.5:
        raise HTTPException(status_code=422, detail="ข้อมูลของสถานีไม่พอสำหรับพยากรณ์")

    value, method = _forecast(row, request.horizon_hours)
    rounded = round(value, 2)
    based_on = pd.Timestamp(row["timestamp"].iloc[0])
    quality = air_quality(rounded)
    return PredictResponse(
        station_id=request.station_id,
        based_on=based_on,
        predicted_for=based_on + pd.Timedelta(hours=request.horizon_hours),
        pm25=rounded,
        horizon_hours=request.horizon_hours,
        method=method,
        feature_coverage=round(coverage, 2),
        level=quality["level"],
        color=quality["color"],
        model_trained_at=state.artifact["trained_at"],
    )
