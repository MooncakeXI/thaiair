"""สร้างตารางฟีเจอร์จากข้อมูลดิบแนวยาว

ขั้นตอน: long → wide → เพิ่มฟีเจอร์จากอดีต → ใส่ค่าเป้าหมายจากอนาคต

กรอบของปัญหา:
    หนึ่งแถว = เวลา t ของสถานีหนึ่ง
    ฟีเจอร์  = สิ่งที่รู้แล้ว ณ เวลา t (รวมค่า ณ t เอง)
    เป้าหมาย = pm25 ที่เวลา t + horizon
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from thaiair.data.schema import BANGKOK_UTC_OFFSET

TARGET = "pm25"

LAGS = (1, 2, 3, 24, 168)
ROLLING_WINDOWS = (3, 24)

# คอลัมน์ที่บอกว่า "แถวนี้คือใคร" — ไม่ใช่ฟีเจอร์
INDEX_COLS = ["timestamp", "station_id"]


def to_wide(long: pd.DataFrame) -> pd.DataFrame:
    """long → wide: หนึ่งแถวต่อ (เวลา, สถานี) · พารามิเตอร์กลายเป็นคอลัมน์

    ใช้ .pivot() ไม่ใช่ .pivot_table() โดยตั้งใจ:
    ถ้ามีคีย์ซ้ำ pivot จะโยน error ส่วน pivot_table จะ "เฉลี่ยให้เงียบๆ"
    ซึ่งกลบบั๊กข้อมูลซ้ำที่เราอุตส่าห์เขียนเทสต์ดักไว้ตั้งแต่ขั้น 2
    """
    wide = long.pivot(index=INDEX_COLS, columns="parameter", values="value")
    wide.columns.name = None
    return wide.reset_index()


def hourly_grid(wide: pd.DataFrame) -> pd.DataFrame:
    """เติมชั่วโมงที่หายไป เพื่อให้ lag N หมายถึง N ชั่วโมงจริง"""
    if wide.empty:
        return wide

    value_columns = [column for column in wide.columns if column not in INDEX_COLS]
    frames = []
    for station_id, group in wide.groupby("station_id", sort=False):
        hourly = group.set_index("timestamp")[value_columns].sort_index().asfreq("h").reset_index()
        hourly["station_id"] = station_id
        frames.append(hourly)

    return pd.concat(frames, ignore_index=True).loc[:, [*INDEX_COLS, *value_columns]]


def build_features(long: pd.DataFrame, *, horizon: int = 1) -> pd.DataFrame:
    """สร้างตารางฟีเจอร์ + คอลัมน์ target"""
    out = hourly_grid(to_wide(long))

    # ⚠️ เรียงก่อนเสมอ — shift/rolling ทำงานตามลำดับแถว ไม่ได้อ่าน timestamp
    out = out.sort_values(INDEX_COLS).reset_index(drop=True)

    # ⚠️ groupby สถานี — ถ้าลืม ค่าของสถานีหนึ่งจะไหลข้ามไปเป็นฟีเจอร์ของอีกสถานี
    # ตรงรอยต่อ โดยไม่มี error ไม่มีอะไรเตือน
    g = out.groupby("station_id", sort=False)[TARGET]

    for lag in LAGS:
        out[f"{TARGET}_lag{lag}"] = g.shift(lag)

    for window in ROLLING_WINDOWS:
        # ต้องการอย่างน้อย 75% ของหน้าต่าง — ไม่ใช่ 100%
        #
        # ข้อมูลจริงมีรูเสมอ และหน้าต่างยิ่งยาวยิ่งเจอรูง่ายขึ้นแบบทวีคูณ:
        # ค่าหาย 3% → หน้าต่าง 24 ชม. มีโอกาสโดน 1−0.97²⁴ ≈ 52%
        # ถ้าเรียกร้องครบ 24 จุด จะเสียข้อมูลไปครึ่งหนึ่งเพื่อความบริสุทธิ์ที่ไม่คุ้ม
        min_periods = max(2, int(window * 0.75))

        out[f"{TARGET}_mean{window}"] = g.transform(
            lambda s, w=window, m=min_periods: s.rolling(w, min_periods=m).mean()
        )
        out[f"{TARGET}_std{window}"] = g.transform(
            lambda s, w=window, m=min_periods: s.rolling(w, min_periods=m).std()
        )

    # ── เข้ารหัสเวลาแบบวงกลม ────────────────────────────────────
    # ชั่วโมง 23 กับ 0 อยู่ติดกันในความจริง แต่ห่างกัน 23 หน่วยถ้าใส่เป็นตัวเลขดิบ
    # sin/cos วางมันลงบนวงกลมหนึ่งหน่วย ระยะห่างเลยถูกต้อง
    #
    # 💡 นี่คือแนวคิดเดียวกับ phasor ใน CEM II — แทนปริมาณที่เป็นคาบ
    #    ด้วยจุดบนวงกลมหนึ่งหน่วย
    #
    # ⚠️ ใช้ "ชั่วโมงเวลาไทย" ไม่ใช่ UTC เพราะรถติดตอนแปดโมงเป็นเรื่องของเวลาท้องถิ่น
    local_hour = (out["timestamp"].dt.hour.to_numpy() + BANGKOK_UTC_OFFSET) % 24
    doy = out["timestamp"].dt.dayofyear.to_numpy()

    out["hour_sin"] = np.sin(2 * np.pi * local_hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * local_hour / 24)
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

    # ── ค่าเป้าหมาย ─────────────────────────────────────────────
    # shift ติดลบ = ดึงอนาคตมาไว้ที่แถวปัจจุบัน
    # ⚠️ นี่คือที่เดียวในไฟล์นี้ที่ shift ติดลบได้ ถ้าเห็นมันในฟีเจอร์ = รั่วแล้ว
    out["target"] = g.shift(-horizon)

    return out
