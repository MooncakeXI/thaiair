"""แหล่งข้อมูลสังเคราะห์ — สำหรับพัฒนาและสำหรับ CI

ทำไมต้องมีก่อนแหล่งจริง:
1. เขียนชั้นที่อยู่ข้างบน (features / train / serve) ได้เลยโดยไม่ต้องรอ API key
2. CI รันได้โดยไม่ต้องมี secret และไม่ต้องต่อเน็ต
3. สร้างเคสยากๆ ได้ตามใจ — ข้อมูลหาย ค่าพุ่งผิดปกติ สถานีหายกลางคัน
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from thaiair.data.schema import BANGKOK_UTC_OFFSET, conform

STATIONS: tuple[str, ...] = ("bkk-01", "bkk-02", "bkk-03")


MISSING_RATE = 0.03

DEFAULT_END = pd.Timestamp("2026-08-01 00:00:00")


def fetch(
    days: int = 30,
    stations: Sequence[str] = STATIONS,
    seed: int = 0,
    end: pd.Timestamp | str | None = None,
) -> pd.DataFrame:

    rng = np.random.default_rng(seed)
    end_ts = DEFAULT_END if end is None else pd.Timestamp(end)

    ts = pd.date_range(end=end_ts, periods=days * 24, freq="h")

    local_hour = (ts.hour.to_numpy() + BANGKOK_UTC_OFFSET) % 24
    doy = ts.dayofyear.to_numpy()

    frames = []
    for station in stations:
        n = len(ts)

        wind = np.clip(rng.gamma(2.0, 1.2, n), 0, None)

        seasonal = 25 * np.cos(2 * np.pi * (doy - 15) / 365)

        daily = 12 * np.exp(-((local_hour - 8) ** 2) / 6) + 10 * np.exp(
            -((local_hour - 19) ** 2) / 8
        )

        pm25 = 35 + seasonal + daily - 4.0 * wind + rng.normal(0, 6, n)
        pm25 = np.clip(pm25, 2, None)

        temperature = (
            28
            + 4 * np.cos(2 * np.pi * (doy - 110) / 365)
            + 5 * np.sin(2 * np.pi * (local_hour - 9) / 24)
            + rng.normal(0, 1.2, n)
        )
        humidity = np.clip(95 - 1.6 * (temperature - 24) + rng.normal(0, 5, n), 20, 100)

        series = {
            "pm25": pm25,
            "temperature": temperature,
            "humidity": humidity,
            "wind_speed": wind,
        }

        for parameter, values in series.items():
            values = values.copy()
            values[rng.random(n) < MISSING_RATE] = np.nan
            frames.append(
                pd.DataFrame(
                    {
                        "timestamp": ts,
                        "station_id": station,
                        "parameter": parameter,
                        "value": values,
                    }
                )
            )

    return conform(pd.concat(frames, ignore_index=True))
