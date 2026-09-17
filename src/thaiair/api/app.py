"""API เสิร์ฟค่าทำนาย PM2.5

uvicorn thaiair.api.app:app --reload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from thaiair.features.build import build_features
from thaiair.models import artifact

log = logging.getLogger(__name__)


# อ่านจาก env เพื่อให้เทสต์และ Docker ชี้ไปที่อื่นได้โดยไม่ต้องแก้โค้ด
def _model_path() -> Path:
    return Path(os.getenv("PM25_MODEL_PATH", str(artifact.DEFAULT_PATH)))


def _raw_path() -> Path:
    return Path(os.getenv("PM25_RAW_PATH", "data/raw/observations.parquet"))


class _State:
    """ของที่โหลดครั้งเดียวตอนสตาร์ต แล้วอยู่ยาวตลอดอายุ process"""

    artifact: dict[str, Any] | None = None
    features: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return self.artifact is not None and self.features is not None


state = _State()
INDEX_PATH = Path(__file__).with_name("index.html")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """โหลดตอนสตาร์ต ไม่ใช่ตอน request แรก

    ถ้าโหลดตอน request แรก คนแรกที่เรียกจะรอหลายวินาที
    และแย่กว่านั้นคือ /ready จะตอบว่าพร้อมทั้งที่ยังไม่พร้อม
    """
    try:
        state.artifact = artifact.load(_model_path())
        raw = pd.read_parquet(_raw_path())
        state.features = build_features(raw, horizon=state.artifact["horizon"])
        log.info(
            "พร้อมเสิร์ฟ — โมเดลเทรนเมื่อ %s · ประวัติ %d แถว",
            state.artifact["trained_at"],
            len(state.features),
        )
    except Exception:
        # ⚠️ ตั้งใจไม่ให้ crash
        # ถ้า process ตาย Kubernetes จะ restart วนไม่จบโดยไม่มีใครได้อ่าน log
        # ปล่อยให้ขึ้นมาแล้วให้ /ready ตอบ 503 แทน — เข้าไปดูสาเหตุได้
        log.exception("โหลดโมเดลไม่สำเร็จ — process ยังอยู่แต่เสิร์ฟไม่ได้")

    yield

    state.artifact = None
    state.features = None


app = FastAPI(title="Thai Air — PM2.5 forecast", lifespan=lifespan)


class PredictRequest(BaseModel):
    station_id: str = Field(examples=["bkk-01"])
    # ไม่ระบุ = ใช้ข้อมูลล่าสุดที่มี
    timestamp: datetime | None = None


class PredictResponse(BaseModel):
    station_id: str
    based_on: datetime  # ใช้ข้อมูล ณ เวลานี้
    predicted_for: datetime  # ทำนายค่าของเวลานี้
    pm25: float
    horizon_hours: int
    model_trained_at: str


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(INDEX_PATH, media_type="text/html")


@app.get("/health")
def health() -> dict[str, str]:
    """process ยังอยู่ไหม — ไม่สนว่าเสิร์ฟได้หรือเปล่า

    ตอบคำถามว่า "ต้อง restart ตัวนี้ไหม"
    """
    return {"status": "alive"}


@app.get("/ready")
def ready() -> dict[str, Any]:
    """เสิร์ฟได้จริงหรือยัง

    ตอบคำถามว่า "ส่ง traffic มาได้หรือยัง" — คนละคำถามกับ /health

    ถ้ารวมสองอันเป็นอันเดียว: pod ที่โมเดลยังโหลดไม่เสร็จจะถูกตัดสินว่า "ตาย"
    แล้วโดน restart ซ้ำไปเรื่อยๆ ทั้งที่มันแค่ยังไม่พร้อม
    """
    if not state.ready:
        raise HTTPException(status_code=503, detail="ยังโหลดโมเดลไม่สำเร็จ")
    return {
        "status": "ready",
        "model_trained_at": state.artifact["trained_at"],
        "horizon_hours": state.artifact["horizon"],
        "history_rows": len(state.features),
    }


@app.get("/stations")
def stations() -> dict[str, list[str]]:
    if not state.ready:
        raise HTTPException(status_code=503, detail="ยังโหลดโมเดลไม่สำเร็จ")
    return {"stations": sorted(state.features["station_id"].unique())}


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    if not state.ready:
        raise HTTPException(status_code=503, detail="ยังโหลดโมเดลไม่สำเร็จ")

    frame = state.features
    rows = frame[frame["station_id"] == request.station_id]
    if rows.empty:
        known = sorted(frame["station_id"].unique())
        raise HTTPException(
            status_code=404,
            detail=f"ไม่รู้จักสถานี {request.station_id!r} — ที่มีคือ {known}",
        )

    if request.timestamp is None:
        row = rows.iloc[[-1]]
    else:
        ts = pd.Timestamp(request.timestamp)
        # ⚠️ ข้อตกลงจากขั้น 1 โผล่มาอีกครั้งที่ขอบระบบ
        # ข้อมูลเราเป็น UTC แบบไม่มี tz — ถ้าคนเรียกส่ง tz มาต้องแปลงก่อนเทียบ
        # ไม่งั้นเทียบไม่ตรงแล้วตอบ 404 ทั้งที่ข้อมูลมีอยู่
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)

        row = rows[rows["timestamp"] == ts]
        if row.empty:
            raise HTTPException(
                status_code=404,
                detail=f"ไม่มีข้อมูลของ {request.station_id} ที่เวลา {ts} (UTC)",
            )

    # ⚠️⚠️ บรรทัดที่กัน train/serve skew
    # เลือก "และเรียง" คอลัมน์ตามรายการที่บันทึกไว้ตอนเทรน ไม่ใช่ตามที่ DataFrame บังเอิญเป็น
    # ถ้าเรียงผิด โมเดลจะอ่านค่าผิดช่องแล้วตอบเลขที่ดูสมเหตุสมผลแต่ผิดสนิท
    features = row[state.artifact["feature_columns"]]

    value = float(state.artifact["model"].predict(features)[0])
    based_on = row["timestamp"].iloc[0]
    horizon = state.artifact["horizon"]

    return PredictResponse(
        station_id=request.station_id,
        based_on=based_on,
        predicted_for=based_on + pd.Timedelta(hours=horizon),
        pm25=round(value, 2),
        horizon_hours=horizon,
        model_trained_at=state.artifact["trained_at"],
    )
