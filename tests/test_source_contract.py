"""เทสต์ที่บังคับสัญญาของแหล่งข้อมูล

หัวใจอยู่ที่ fixture ข้างล่าง: มัน parametrize จาก SOURCES โดยตรง
แปลว่าแหล่งใหม่ที่ลงทะเบียนแล้ว "ถูกเทสต์ทันที" โดยไม่ต้องมีใครจำได้ว่าต้องเขียนเทสต์
"""

from __future__ import annotations

import json
import pkgutil
from pathlib import Path

import httpx
import pandas as pd
import pytest

import thaiair.data.sources as sources_pkg
from thaiair.data.schema import KEY, PARAMETERS, SCHEMA
from thaiair.data.sources import SOURCES, openmeteo

FIXTURES = Path(__file__).parent / "fixtures"
# ชื่อโมดูลที่ไม่นับเป็นแหล่งข้อมูล
NOT_A_SOURCE = {"base"}


@pytest.fixture(params=sorted(SOURCES), ids=sorted(SOURCES))
def frame(request: pytest.FixtureRequest) -> pd.DataFrame:
    name = request.param
    kwargs = OFFLINE_KWARGS[name]() if name in OFFLINE_KWARGS else {}
    client = kwargs.get("client")
    try:
        yield SOURCES[name](days=3, **kwargs)
    finally:
        if client is not None:
            client.close()


def test_has_exactly_the_contract_columns(frame):
    assert list(frame.columns) == list(SCHEMA)


def test_dtypes_match_contract(frame):
    for column, expected in SCHEMA.items():
        assert str(frame[column].dtype) == expected, (
            f"คอลัมน์ {column!r} เป็น {frame[column].dtype} แต่สัญญาบอกว่าต้องเป็น {expected}"
        )


def test_timestamp_is_naive_utc(frame):
    # ถ้ามี tz ติดมา แปลว่าแหล่งข้อมูลไม่ได้ผ่าน conform() หรือ conform() พัง
    assert frame["timestamp"].dt.tz is None


def test_sorted_by_key(frame):
    assert frame[KEY].equals(frame[KEY].sort_values(KEY).reset_index(drop=True))


def test_no_duplicate_keys(frame):
    assert not frame.duplicated(KEY).any()


def test_parameters_are_known(frame):
    unknown = set(frame["parameter"].dropna().unique()) - set(PARAMETERS)
    assert not unknown, f"พารามิเตอร์ที่ไม่รู้จัก: {sorted(unknown)}"


def test_returns_rows(frame):
    # แหล่งที่คืนตารางว่างผ่านเทสต์ข้างบนทุกข้อได้หมด — ต้องดักไว้
    assert len(frame) > 0


def test_every_source_module_is_registered():
    """โมดูลทุกตัวในโฟลเดอร์ sources/ ต้องอยู่ในทะเบียน

    เทสต์ข้างบนครอบคลุมทุกแหล่ง "ที่ลงทะเบียนแล้ว" อัตโนมัติ
    แต่ถ้าคุณเขียนแหล่งใหม่แล้วลืมลงทะเบียน มันจะหลุดทุกด่าน — เทสต์นี้ดักตรงนั้น
    """
    modules = {
        m.name
        for m in pkgutil.iter_modules(sources_pkg.__path__)
        if not m.name.startswith("_") and m.name not in NOT_A_SOURCE
    }
    assert modules == set(SOURCES), (
        f"เขียนแล้วแต่ไม่ได้ลงทะเบียน: {sorted(modules - set(SOURCES))} · "
        f"ลงทะเบียนแล้วแต่ไม่มีโมดูล: {sorted(set(SOURCES) - modules)}"
    )


def _canned_client(payload: dict) -> httpx.Client:
    """client ที่ตอบด้วย payload เดิมเสมอ ไม่แตะเน็ต"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _openmeteo_offline() -> dict:
    payload = json.loads((FIXTURES / "openmeteo_air_quality.json").read_text())
    return {"client": _canned_client(payload)}


# แหล่งที่ต้องใช้เน็ต → ต้องมีวิธีทำให้ทำงานแบบออฟไลน์
OFFLINE_KWARGS = {
    "openmeteo": _openmeteo_offline,
}


def test_openmeteo_never_sends_timezone_param():
    """กันคนเติม timezone= เข้าไปในอนาคต

    ด่านใน parse_air_quality() ตรวจ "คำตอบ"
    เทสต์ตัวนี้ตรวจ "คำขอ" — สองชั้นคนละจุด
    """
    payload = json.loads((FIXTURES / "openmeteo_air_quality.json").read_text())
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        openmeteo.fetch(days=1, locations=["bangkok"], client=client)

    assert seen, "ไม่มีการยิง request เลย"
    for params in seen:
        assert "timezone" not in params, f"เผลอส่ง timezone ไป: {params}"


@pytest.mark.live
def test_openmeteo_live_still_matches_our_parser():
    """ยิง API จริงเพื่อดูว่าเขายังไม่เปลี่ยนรูปแบบ

    ไม่รันโดยปริยาย — สั่งเองด้วย `pytest -m live`
    รันสัปดาห์ละครั้งก็พอ วันที่มันแดงคือวันที่ Open-Meteo เปลี่ยน API
    """
    df = openmeteo.fetch(days=1, locations=["bangkok"])
    assert len(df) > 0
    assert set(df.columns) == set(SCHEMA)
