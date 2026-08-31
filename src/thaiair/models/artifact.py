"""บันทึกและโหลดโมเดลพร้อมประวัติของมัน

โมเดลเปล่าๆ ไม่พอ — ต้องรู้ด้วยว่ามันต้องการฟีเจอร์อะไร ทำนายไกลแค่ไหน
เทรนด้วยข้อมูลช่วงไหน และตอนเทรนทำได้ดีแค่ไหน
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib

DEFAULT_PATH = Path("models/pm25.joblib")

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


def _check(payload: dict[str, Any], action: str) -> None:
    missing = REQUIRED_KEYS - set(payload)
    if missing:
        raise ValueError(f"{action}: artifact ขาดคีย์ {sorted(missing)}")


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
