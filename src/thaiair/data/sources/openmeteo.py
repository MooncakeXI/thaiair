"""แหล่งข้อมูลจริงตัวแรก — Open-Meteo Air Quality (ไม่ต้องใช้ API key)

⚠️ ข้อจำกัดที่ต้องจำ: PM2.5 จากที่นี่มาจาก**แบบจำลอง** (CAMS) ไม่ใช่เครื่องวัดที่สถานี
ใช้เป็นฟีเจอร์และใช้เทียบได้ดี แต่ค่าเป้าหมายที่จะทำนายควรเป็นค่าวัดจริง
(ไม่งั้นเรากำลังทำนายผลลัพธ์ของแบบจำลองอื่น ซึ่งวนอยู่ในตัวเอง)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import httpx
import pandas as pd

from thaiair.data.http import get_json
from thaiair.data.schema import conform

log = logging.getLogger(__name__)

BASE_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# พิกัดที่สนใจ — key จะกลายเป็นส่วนหนึ่งของ station_id
LOCATIONS: dict[str, tuple[float, float]] = {
    "bangkok": (13.7563, 100.5018),
    "chiangmai": (18.7883, 98.9853),
}

# ชื่อตัวแปรฝั่ง Open-Meteo → ชื่อพารามิเตอร์ตามสัญญาของเรา
# หน่วยของเขาเป็น μg/m³ อยู่แล้ว ตรงกับ PARAMETERS ใน schema.py จึงไม่ต้องแปลง
PARAMETER_MAP = {
    "pm2_5": "pm25",
    "pm10": "pm10",
}

# นำหน้า station_id ด้วยชื่อแหล่ง — เหตุผลอยู่ในหมายเหตุท้ายไฟล์
SOURCE_PREFIX = "om"

MAX_PAST_DAYS = 92


def parse_air_quality(payload: dict[str, Any], station_id: str) -> pd.DataFrame:
    """แปลง JSON ของ Open-Meteo เป็นตารางแนวยาว

    เป็นฟังก์ชันบริสุทธิ์ — รับ dict คืน DataFrame ไม่ยุ่งกับเน็ตเลย
    เทสต์ตัวนี้ได้โดยไม่ต้องต่ออินเทอร์เน็ต ซึ่งคือเหตุผลที่แยกมันออกมา
    """
    # ⚠️ ด่านกันข้อมูลเลื่อน 7 ชั่วโมง — บรรทัดสำคัญที่สุดในไฟล์นี้
    #
    # เราจงใจ "ไม่ส่ง" พารามิเตอร์ timezone ไป เพื่อให้ API คืนเวลา UTC
    # ถ้าวันหนึ่งมีคนเติม timezone=Asia/Bangkok เข้าไปด้วยความหวังดี
    # API จะคืนเวลาไทยแบบไม่มี tz ติดมา แล้ว conform() จะเข้าใจว่าเป็น UTC
    # ข้อมูลทั้งชุดเลื่อนไป 7 ชม. โดยไม่มีอะไรพัง ไม่มีอะไรเตือน
    # บรรทัดข้างล่างคือสิ่งเดียวที่จะฟ้อง
    tz = payload.get("timezone")
    if tz not in {"GMT", "UTC"}:
        raise ValueError(
            f"คาดว่าจะได้เวลา UTC แต่ API บอกว่า timezone={tz!r} — "
            "เช็คว่ามีใครเผลอส่งพารามิเตอร์ timezone ไปหรือเปล่า"
        )

    hourly = payload.get("hourly")
    if not hourly or "time" not in hourly:
        raise ValueError("ไม่พบ hourly.time ในคำตอบ — รูปแบบ API อาจเปลี่ยนไปแล้ว")

    times = hourly["time"]

    frames = []
    for api_name, our_name in PARAMETER_MAP.items():
        values = hourly.get(api_name)
        if values is None:
            log.warning("ไม่มี %s ในคำตอบสำหรับ %s — ข้าม", api_name, station_id)
            continue

        if len(values) != len(times):
            raise ValueError(
                f"{api_name} มี {len(values)} ค่า แต่ time มี {len(times)} ค่า — "
                "array ไม่ขนานกัน แปลว่าสมมติฐานเรื่องรูปแบบ API ผิดแล้ว"
            )

        frames.append(
            pd.DataFrame(
                {
                    "timestamp": times,
                    "station_id": station_id,
                    "parameter": our_name,
                    "value": values,  # null ของ JSON จะกลายเป็น NaN — ตั้งใจให้เก็บไว้
                }
            )
        )

    if not frames:
        raise ValueError("ไม่ได้พารามิเตอร์ที่ต้องการสักตัวเดียว")

    return pd.concat(frames, ignore_index=True)


def fetch(
    *,
    days: int = 30,
    locations: Sequence[str] | None = None,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """ดึงข้อมูลคุณภาพอากาศย้อนหลังจาก Open-Meteo

    `client` มีไว้ให้เทสต์ส่ง MockTransport เข้ามา — โค้ดจริงไม่ต้องส่ง
    """
    names = tuple(locations) if locations else tuple(LOCATIONS)

    past_days = max(1, days)
    if past_days > MAX_PAST_DAYS:
        # ตัดเงียบๆ คือการโกหกผู้เรียก — บอกให้รู้
        log.warning(
            "ขอ %d วัน แต่ Open-Meteo ให้ย้อนหลังได้สูงสุด %d วัน — ตัดให้แล้ว",
            days, MAX_PAST_DAYS,
        )
        past_days = MAX_PAST_DAYS

    frames = []
    for name in names:
        latitude, longitude = LOCATIONS[name]
        payload = get_json(
            BASE_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": ",".join(PARAMETER_MAP),
                "past_days": past_days,
                "forecast_days": 1,  # เอาแต่ของที่ผ่านมาแล้ว ไม่เอาค่าพยากรณ์
                # ⚠️ ห้ามใส่ "timezone" ที่นี่ — ดูเหตุผลใน parse_air_quality()
            },
            client=client,
        )
        frames.append(parse_air_quality(payload, f"{SOURCE_PREFIX}:{name}"))

    raw = pd.concat(frames, ignore_index=True)

    # forecast_days=1 จำเป็นเพื่อให้ได้ข้อมูล "วันนี้" แต่มันแถมค่าพยากรณ์มาด้วย
    # ตารางดิบต้องเก็บเฉพาะ "สิ่งที่เกิดขึ้นแล้ว" เท่านั้น
    #
    # ถ้าปล่อยค่าพยากรณ์ปนเข้ามา วันหนึ่งโมเดลจะถูกเทรนด้วยค่าที่ตอนนั้น
    # "ยังไม่เกิดขึ้นจริง" — เป็น data leakage คนละแบบกับที่เราจะกันในขั้น 4
    # แต่ตามหายากกว่ามาก เพราะไม่มีอะไรในตารางบอกว่าแถวไหนเป็นพยากรณ์
    now = pd.Timestamp.now("UTC").tz_localize(None)
    raw = raw[pd.to_datetime(raw["timestamp"]) <= now]

    return conform(raw)