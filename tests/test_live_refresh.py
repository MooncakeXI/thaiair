import pandas as pd

from thaiair.api import live
from thaiair.data.schema import conform


def test_refresh_keeps_working_when_one_station_fails(monkeypatch):
    stations = [
        {"station_id": "s1", "sensor_id": 1},
        {"station_id": "s2", "sensor_id": 2},
    ]
    raw = conform(
        pd.DataFrame(
            [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "station_id": station["station_id"],
                    "parameter": "pm25",
                    "value": 10,
                }
                for station in stations
            ]
        )
    )

    monkeypatch.setattr(live.openaq, "discover", lambda **_: stations)

    def fetch_latest(station, **_):
        if station["station_id"] == "s2":
            raise RuntimeError("sensor down")
        return conform(
            pd.DataFrame(
                [
                    {
                        "timestamp": "2026-01-01T01:00:00Z",
                        "station_id": "s1",
                        "parameter": "pm25",
                        "value": 12,
                    }
                ]
            )
        )

    monkeypatch.setattr(live.openaq, "fetch_latest", fetch_latest)
    pauses = []
    merged, discovered, success_count = live.refresh(
        raw,
        stations,
        api_key="test",
        client=object(),
        pace_seconds=1.1,
        sleep=pauses.append,
    )

    assert success_count == 1
    assert discovered == stations
    assert merged.loc[merged["station_id"] == "s1", "value"].iloc[-1] == 12
    assert pauses == [1.1]
