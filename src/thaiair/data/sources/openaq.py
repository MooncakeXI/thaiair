"""ข้อมูล PM2.5 ที่วัดจริงจากสถานี OpenAQ ในกรุงเทพ"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
import pandas as pd

from thaiair.data.http import get_json
from thaiair.data.schema import conform

BASE_URL = "https://api.openaq.org/v3"
BANGKOK = "13.7563,100.5018"
RADIUS_METERS = 25_000
PM25_PARAMETER_ID = 2
PAGE_SIZE = 1_000
SOURCE_PREFIX = "oa"

log = logging.getLogger(__name__)


def _key(api_key: str | None) -> str:
    key = (api_key or os.getenv("OPENAQ_API_KEY", "")).strip()
    if not key:
        raise ValueError("ต้องตั้ง OPENAQ_API_KEY ก่อนใช้ source openaq")
    return key


def _results(payload: dict[str, Any], resource: str) -> list[dict[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError(f"OpenAQ ไม่คืน results สำหรับ {resource} — รูปแบบ API อาจเปลี่ยน")
    return results


def _pm25_sensors(payload: dict[str, Any]) -> list[tuple[int, int]]:
    sensors = []
    for location in _results(payload, "locations"):
        if not location.get("isMonitor") or location.get("isMobile"):
            continue
        for sensor in location.get("sensors", []):
            parameter = sensor.get("parameter", {})
            if parameter.get("id") == PM25_PARAMETER_ID:
                sensors.append((int(location["id"]), int(sensor["id"])))
    return sorted(set(sensors))


def _unit_is_ug_m3(unit: Any) -> bool:
    normalized = str(unit).lower().replace("µ", "u").replace("μ", "u").replace("³", "3")
    return normalized.replace(" ", "") == "ug/m3"


def _parse_hours(rows: list[dict[str, Any]], station_id: str) -> list[dict[str, Any]]:
    parsed = []
    for row in rows:
        parameter = row.get("parameter", {})
        if parameter.get("id") != PM25_PARAMETER_ID or parameter.get("name") != "pm25":
            raise ValueError(f"sensor {station_id} ไม่ใช่ PM2.5 ตามที่ OpenAQ discovery แจ้ง")
        if not _unit_is_ug_m3(parameter.get("units")):
            raise ValueError(f"sensor {station_id} ใช้หน่วยที่ไม่รองรับ: {parameter.get('units')!r}")

        period = row.get("period") or {}
        timestamp = (period.get("datetimeFrom") or {}).get("utc")
        if not timestamp:
            raise ValueError(f"ข้อมูลของ sensor {station_id} ไม่มี period.datetimeFrom.utc")

        parsed.append(
            {
                "timestamp": timestamp,
                "station_id": station_id,
                "parameter": "pm25",
                "value": row.get("value"),
            }
        )
    return parsed


def fetch(
    *,
    days: int = 30,
    api_key: str | None = None,
    end: pd.Timestamp | str | None = None,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """ดึงค่าเฉลี่ยรายชั่วโมงจาก reference monitors ภายใน 25 กม. ของกรุงเทพ"""
    key = _key(api_key)
    owns_client = client is None
    client = client or httpx.Client(headers={"X-API-Key": key})
    if not owns_client:
        client.headers["X-API-Key"] = key

    try:
        locations = get_json(
            f"{BASE_URL}/locations",
            {
                "coordinates": BANGKOK,
                "radius": RADIUS_METERS,
                "parameters_id": PM25_PARAMETER_ID,
                "monitor": True,
                "mobile": False,
                "limit": PAGE_SIZE,
                "page": 1,
            },
            client=client,
        )
        sensors = _pm25_sensors(locations)
        if not sensors:
            raise ValueError("ไม่พบ reference monitor ที่วัด PM2.5 ภายใน 25 กม. ของกรุงเทพ")

        end_ts = pd.Timestamp.now(tz="UTC") if end is None else pd.Timestamp(end)
        end_ts = end_ts.tz_localize("UTC") if end_ts.tzinfo is None else end_ts.tz_convert("UTC")
        start_ts = end_ts - pd.Timedelta(days=max(1, days))

        records = []
        for location_id, sensor_id in sensors:
            station_id = f"{SOURCE_PREFIX}:{location_id}:{sensor_id}"
            sensor_records = []
            page = 1
            try:
                while True:
                    payload = get_json(
                        f"{BASE_URL}/sensors/{sensor_id}/hours",
                        {
                            "datetime_from": start_ts.isoformat(),
                            "datetime_to": end_ts.isoformat(),
                            "limit": PAGE_SIZE,
                            "page": page,
                        },
                        client=client,
                    )
                    rows = _results(payload, f"sensor {sensor_id} hours")
                    sensor_records.extend(_parse_hours(rows, station_id))
                    if len(rows) < PAGE_SIZE:
                        break
                    page += 1
            except RuntimeError as exc:
                log.warning("ข้าม sensor %s เพราะ OpenAQ ตอบไม่สำเร็จ: %s", sensor_id, exc)
                continue
            records.extend(sensor_records)

        if not records:
            raise ValueError("OpenAQ ไม่คืนข้อมูล PM2.5 ในช่วงเวลาที่ขอ")
        return conform(pd.DataFrame.from_records(records))
    finally:
        if owns_client:
            client.close()
