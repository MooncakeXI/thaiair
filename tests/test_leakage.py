"""เทสต์ที่พิสูจน์ว่าฟีเจอร์ไม่ได้มองอนาคต

นี่คือเหตุผลทั้งหมดที่ขั้น 4 มีอยู่

บั๊ก leakage ไม่ทำให้อะไรพัง ไม่มี error ไม่มี warning
มันแค่ทำให้โมเดล "ดูเก่ง" ตอนวัดผล แล้วพังตอนใช้งานจริง
และกว่าจะรู้ตัวก็ตอนที่มันบอกคนผิดไปแล้วหลายเดือน
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thaiair.data.schema import conform
from thaiair.features.build import LAGS, ROLLING_WINDOWS, TARGET, build_features


@pytest.fixture
def walk() -> pd.DataFrame:
    """ข้อมูล random walk สองสถานี — ค่าทุกจุดไม่ซ้ำกัน

    ทำไมต้อง random walk ไม่ใช่ค่าคงที่หรือเส้นตรง:
    เทสต์นี้ทำงานด้วยการ "แก้ค่าหนึ่งจุด แล้วดูว่ามีอะไรขยับบ้าง"
    ถ้าค่าในชุดข้อมูลซ้ำๆ กัน การรั่วอาจไม่ทำให้ตัวเลขเปลี่ยน แล้วเทสต์จะเขียวทั้งที่รั่ว
    """
    rng = np.random.default_rng(0)
    ts = pd.date_range("2026-01-01", periods=300, freq="h")

    frames = []
    for station in ("s1", "s2"):
        values = 30 + np.cumsum(rng.normal(0, 1.5, len(ts)))
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": ts,
                    "station_id": station,
                    "parameter": "pm25",
                    "value": values,
                }
            )
        )
    return conform(pd.concat(frames, ignore_index=True))


def test_features_never_see_the_future(walk):
    """แก้ค่าที่เวลา T → ฟีเจอร์ทุกตัวที่เวลา < T ต้องไม่ขยับแม้แต่นิดเดียว

    เทสต์นี้ทรงพลังเพราะมันไม่ต้องรู้ว่าฟีเจอร์แต่ละตัวคำนวณยังไง
    มันบังคับ "คุณสมบัติ" ไม่ใช่ "วิธีการ" — เพิ่มฟีเจอร์ใหม่กี่ตัวก็ยังคุ้มครองอัตโนมัติ
    """
    cut = pd.Timestamp("2026-01-08 00:00:00")

    before = build_features(walk, horizon=1)

    tampered = walk.copy()
    mask = (tampered["timestamp"] == cut) & (tampered["station_id"] == "s1")
    assert mask.sum() == 1, "ควรเจอแถวเดียว — ถ้าไม่ใช่แสดงว่า fixture ผิด"
    tampered.loc[mask, "value"] = 9999.0

    after = build_features(tampered, horizon=1)

    past = before["timestamp"] < cut

    # target ได้รับอนุญาตให้เห็นอนาคต — มันคือสิ่งที่เราจะทำนาย
    # ฟีเจอร์ทุกตัวที่เหลือห้ามเห็น
    feature_cols = [c for c in before.columns if c != "target"]

    pd.testing.assert_frame_equal(
        before.loc[past, feature_cols],
        after.loc[past, feature_cols],
    )


def test_stations_do_not_bleed_into_each_other():
    """ฟีเจอร์ของสถานีหนึ่งต้องไม่มีค่าจากอีกสถานีปนมา

    ใช้สองสถานีที่ค่าต่างกันคนละโลก (10 กับ 999)
    ถ้าลืม groupby ค่า 999 จะไหลข้ามมาที่สถานี low ตรงรอยต่อ
    """
    ts = pd.date_range("2026-01-01", periods=50, freq="h")

    frames = [
        pd.DataFrame({"timestamp": ts, "station_id": station, "parameter": "pm25", "value": level})
        for station, level in (("low", 10.0), ("high", 999.0))
    ]
    long = conform(pd.concat(frames, ignore_index=True))

    features = build_features(long, horizon=1)
    low = features[features["station_id"] == "low"]

    carried = [c for c in features.columns if "lag" in c or "mean" in c]
    for column in carried:
        values = low[column].dropna()
        assert (values == 10.0).all(), f"{column} มีค่าจากสถานีอื่นปนมา"


@pytest.mark.parametrize("horizon", [1, 24])
def test_target_is_exactly_the_horizon_value(walk, horizon):
    """target ที่แถว t ต้องเท่ากับ pm25 ที่แถว t+horizon ของสถานีเดียวกัน"""
    features = build_features(walk, horizon=horizon)
    s1 = features[features["station_id"] == "s1"].reset_index(drop=True)

    expected = s1["pm25"].iloc[horizon:].reset_index(drop=True)
    actual = s1["target"].iloc[:-horizon].reset_index(drop=True)

    pd.testing.assert_series_equal(actual, expected, check_names=False)


def test_expected_feature_columns_are_present(walk):
    """ฟีเจอร์ที่ประกาศไว้ต้องมีอยู่จริงทุกคอลัมน์

    ฟีเจอร์ที่หายไปเงียบๆ ไม่ทำให้อะไรพัง — โมเดลแค่เทรนด้วยข้อมูลน้อยลง
    แล้วแย่ลงโดยไม่มีใครรู้ว่าเพราะอะไร
    """
    features = build_features(walk, horizon=1)

    expected = (
        {f"{TARGET}_lag{lag}" for lag in LAGS}
        | {f"{TARGET}_mean{w}" for w in ROLLING_WINDOWS}
        | {f"{TARGET}_std{w}" for w in ROLLING_WINDOWS}
        | {"hour_sin", "hour_cos", "doy_sin", "doy_cos", "target"}
    )
    missing = expected - set(features.columns)
    assert not missing, f"ฟีเจอร์หายไป: {sorted(missing)}"
