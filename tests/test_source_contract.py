"""เทสต์ที่บังคับสัญญาของแหล่งข้อมูล

หัวใจอยู่ที่ fixture ข้างล่าง: มัน parametrize จาก SOURCES โดยตรง
แปลว่าแหล่งใหม่ที่ลงทะเบียนแล้ว "ถูกเทสต์ทันที" โดยไม่ต้องมีใครจำได้ว่าต้องเขียนเทสต์
"""

from __future__ import annotations

import pkgutil

import pandas as pd
import pytest

import thaiair.data.sources as sources_pkg
from thaiair.data.schema import KEY, PARAMETERS, SCHEMA
from thaiair.data.sources import SOURCES

# ชื่อโมดูลที่ไม่นับเป็นแหล่งข้อมูล
NOT_A_SOURCE = {"base"}


@pytest.fixture(params=sorted(SOURCES), ids=sorted(SOURCES))
def frame(request: pytest.FixtureRequest) -> pd.DataFrame:
    """ดึงข้อมูลช่วงสั้นๆ จากทุกแหล่งในทะเบียน ทีละแหล่ง"""
    return SOURCES[request.param](days=3)


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