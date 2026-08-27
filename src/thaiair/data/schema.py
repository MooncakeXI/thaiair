"""สัญญาของข้อมูลดิบ — ทุกแหล่งข้อมูลต้องคืนตารางหน้าตาแบบนี้เท่านั้น

รูปแบบเป็น "แนวยาว": หนึ่งแถว = หนึ่งค่าที่วัดได้ ณ เวลาหนึ่ง สถานีหนึ่ง พารามิเตอร์หนึ่ง
เพิ่มพารามิเตอร์ใหม่จึงไม่ต้องแตะสัญญานี้เลย
"""

from __future__ import annotations

import pandas as pd

# หน่วยมาตรฐานของแต่ละพารามิเตอร์
#
# สังเกตว่าตารางไม่มีคอลัมน์ "unit" — ตั้งใจ
# ถ้ามีคอลัมน์หน่วย วันหนึ่งจะมีแถวที่หน่วยไม่ตรงปนเข้ามาแล้วไม่มีใครรู้ตัว
# บังคับให้แปลงหน่วยที่ชั้นแหล่งข้อมูลแทน แล้วในตารางนี้หน่วยจึงเป็นหนึ่งเดียวเสมอ
PARAMETERS: dict[str, str] = {
    "pm25": "ug/m3",
    "pm10": "ug/m3",
    "temperature": "celsius",
    "humidity": "percent",
    "wind_speed": "m/s",
    "wind_direction": "degrees",
}

SCHEMA: dict[str, str] = {
    "timestamp": "datetime64[ns]",  # UTC เสมอ และไม่มี tz ติดมา
    "station_id": "string",
    "parameter": "string",
    "value": "float64",
}

# สามคอลัมน์นี้รวมกันคือ "ตัวตน" ของหนึ่งแถว
KEY = ["timestamp", "station_id", "parameter"]


def conform(df: pd.DataFrame) -> pd.DataFrame:
    """บังคับตารางให้ตรงตามสัญญา — ทุกแหล่งข้อมูลต้องเรียกฟังก์ชันนี้ก่อนคืนค่า

    ⚠️ ฟังก์ชันนี้ถือว่า timestamp ที่ "ไม่มี tz ติดมา" คือ UTC อยู่แล้ว

    ถ้าแหล่งข้อมูลของคุณคืนเวลาไทยแบบไม่มี tz (Air4Thai เป็นแบบนั้น)
    ต้องแปลงเป็น UTC *ก่อน* เรียกฟังก์ชันนี้
    ไม่งั้นข้อมูลจะเลื่อนไป 7 ชั่วโมงโดยไม่มีอะไรฟ้อง และคุณจะรู้ตัวตอน
    กราฟรายวันมีจุดสูงสุดตอนตีสี่
    """
    missing = set(SCHEMA) - set(df.columns)
    if missing:
        raise ValueError(f"ขาดคอลัมน์ตามสัญญา: {sorted(missing)}")

    out = df.loc[:, list(SCHEMA)].copy()

    # pandas 2.x คืน datetime64[us] หรือ [s] ได้ ขึ้นกับว่า input เป็นอะไร
    # ถ้าไม่บังคับเป็น [ns] จะเจอเทสต์แดงแบบหาสาเหตุไม่เจอตอนเพิ่มแหล่งที่สอง
    ts = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out["timestamp"] = ts.dt.tz_localize(None).astype("datetime64[ns]")

    out["station_id"] = out["station_id"].astype("string")
    out["parameter"] = out["parameter"].astype("string")
    out["value"] = pd.to_numeric(out["value"], errors="coerce").astype("float64")

    # แถวที่ไม่รู้เวลา ใช้ทำอะไรไม่ได้เลย ทิ้งได้
    # แต่แถวที่ value เป็น NaN "เก็บไว้" — เพราะ "วัดแล้วไม่ได้ค่า"
    # เป็นข้อมูลคนละอย่างกับ "ไม่ได้วัด" และโมเดลควรได้เห็นความต่างนั้น
    out = out.dropna(subset=["timestamp"])

    # keep="last" = ถ้าคีย์ซ้ำ ให้ค่าที่มาทีหลังชนะ
    # เพราะแหล่งข้อมูลมักส่งค่าแก้ไขตามมาทีหลัง (ค่าที่ผ่านการตรวจสอบแล้ว)
    out = (
        out.sort_values(KEY)
        .drop_duplicates(subset=KEY, keep="last")
        .reset_index(drop=True)
    )

    return out