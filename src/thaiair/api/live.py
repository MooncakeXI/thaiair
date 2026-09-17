from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from thaiair.data.schema import conform
from thaiair.data.sources import openaq

log = logging.getLogger(__name__)


def load_stations(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    stations = payload.get("stations")
    if not isinstance(stations, list) or not stations:
        raise ValueError(f"station snapshot ที่ {path} ไม่มี stations")
    return stations


def refresh(
    raw: pd.DataFrame,
    snapshot_stations: list[dict[str, Any]],
    *,
    api_key: str,
    pace_seconds: float = 1.1,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[pd.DataFrame, list[dict[str, Any]], int]:
    """ดึงข้อมูลสดอย่างช้า ๆ ให้ไม่เกิน rate limit แล้วรวมกับ snapshot"""
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    known_ids = set(raw["station_id"].unique())

    try:
        try:
            discovered = openaq.discover(api_key=api_key, client=client)
            stations = [station for station in discovered if station["station_id"] in known_ids]
        except Exception:
            log.exception("อัปเดต station metadata ไม่สำเร็จ — ใช้ snapshot เดิม")
            stations = [
                station for station in snapshot_stations if station["station_id"] in known_ids
            ]

        frames = []
        for index, station in enumerate(stations):
            try:
                latest = openaq.fetch_latest(station, api_key=api_key, client=client)
                if not latest.empty:
                    frames.append(latest)
            except Exception as exc:
                log.warning("ข้าม %s ระหว่าง live refresh: %s", station["station_id"], exc)
            if index < len(stations) - 1:
                sleep(pace_seconds)

        if not frames:
            raise RuntimeError("OpenAQ ไม่คืนข้อมูลสดจากสถานีใดเลย")

        merged = conform(pd.concat([raw, *frames], ignore_index=True))
        cutoff = merged["timestamp"].max() - pd.Timedelta(days=31)
        merged = merged[merged["timestamp"] >= cutoff].reset_index(drop=True)
        return merged, stations, len(frames)
    finally:
        if owns_client:
            client.close()
