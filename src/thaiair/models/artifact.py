"""บันทึกและโหลดโมเดลพร้อมประวัติของมัน

โมเดลเปล่าๆ ไม่พอ — ต้องรู้ด้วยว่ามันต้องการฟีเจอร์อะไร ทำนายไกลแค่ไหน
เทรนด้วยข้อมูลช่วงไหน และตอนเทรนทำได้ดีแค่ไหน
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib

DEFAULT_PATH = Path("models/pm25.joblib")
SCHEMA_VERSION = 2
DEFAULT_HORIZONS = (3, 6, 9, 12, 15, 18, 21, 24)

# ทุกคีย์ต้องมีครบ — ตรวจตอนบันทึกและตอนโหลด
REQUIRED_KEYS = frozenset(
    {
        "model",  # ตัวโมเดลที่เทรนแล้ว
        "feature_columns",  # ชื่อ + ลำดับฟีเจอร์ที่โมเดลคาดหวัง
        "horizon",  # ทำนายล่วงหน้ากี่ชั่วโมง
        "trained_at",  # เทรนเมื่อไหร่ (UTC)
        "train_range",  # ข้อมูลเทรนครอบช่วงเวลาไหน
        "metrics",  # ตอนเทรนวัดได้เท่าไหร่
    }
)

V2_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "forecasters",
        "feature_columns",
        "horizons",
        "trained_at",
        "train_range",
    }
)


def _check(payload: dict[str, Any], action: str) -> None:
    required = (
        V2_REQUIRED_KEYS if payload.get("schema_version") == SCHEMA_VERSION else REQUIRED_KEYS
    )
    missing = required - set(payload)
    if missing:
        raise ValueError(f"{action}: artifact ขาดคีย์ {sorted(missing)}")

    if payload.get("schema_version") != SCHEMA_VERSION:
        return

    horizons = tuple(payload["horizons"])
    if horizons != tuple(sorted(set(horizons))) or not horizons:
        raise ValueError(f"{action}: horizons ต้องไม่ซ้ำและเรียงจากน้อยไปมาก")

    forecasters = payload["forecasters"]
    if set(forecasters) != set(horizons):
        raise ValueError(f"{action}: forecasters ไม่ตรงกับ horizons")

    for horizon, forecaster in forecasters.items():
        method = forecaster.get("method")
        if method not in {"model", "persistence"}:
            raise ValueError(f"{action}: horizon {horizon} มี method ไม่ถูกต้อง: {method!r}")
        if method == "model" and forecaster.get("model") is None:
            raise ValueError(f"{action}: horizon {horizon} เลือก model แต่ไม่มีโมเดล")


def horizons(payload: dict[str, Any]) -> tuple[int, ...]:
    if payload.get("schema_version") == SCHEMA_VERSION:
        return tuple(payload["horizons"])
    return (int(payload["horizon"]),)


def forecaster(payload: dict[str, Any], horizon: int) -> dict[str, Any]:
    if payload.get("schema_version") == SCHEMA_VERSION:
        return payload["forecasters"][horizon]
    if horizon != payload["horizon"]:
        raise KeyError(horizon)
    return {"method": "model", "model": payload["model"], "metrics": payload["metrics"]}


def save(payload: dict[str, Any], path: Path = DEFAULT_PATH) -> Path:
    _check(payload, "บันทึกไม่ได้")
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, path)
    return path


def load(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    """โหลดพร้อมตรวจว่าครบ

    ทำไมต้องตรวจตอนโหลด: ไฟล์ที่บันทึกไว้เมื่อสองเดือนก่อนอาจไม่มีคีย์ที่เพิ่งเพิ่ม
    ถ้าไม่ตรวจ มันจะพังตอน API รับ request แรกด้วย KeyError ที่ไม่บอกอะไร
    ตรวจตอนโหลดทำให้พังตอนสตาร์ต ซึ่งเห็นทันทีและแก้ง่ายกว่ามาก
    """
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบโมเดลที่ {path} — รัน `python -m thaiair.models.train` ก่อน")
    payload = joblib.load(path)
    _check(payload, f"โหลดจาก {path} ไม่ได้")
    return payload
