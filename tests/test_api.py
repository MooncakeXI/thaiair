"""เทสต์ชั้นเสิร์ฟ — รวมถึงตัวที่กัน train/serve skew"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import HistGradientBoostingRegressor

from thaiair.data.sources import synthetic
from thaiair.features.build import build_features
from thaiair.models import artifact
from thaiair.models.train import feature_columns

HORIZON = 24
STATION = "bkk-01"


@pytest.fixture(scope="module")
def served(tmp_path_factory, module_mocker=None):
    """สร้างข้อมูล + เทรนโมเดลเล็กๆ แล้วชี้ API มาที่นี่

    เทรนจริง ไม่ใช่ mock — เพราะสิ่งที่อยากพิสูจน์คือ
    "เส้นทางเทรน" กับ "เส้นทางเสิร์ฟ" ให้ผลตรงกันจริงหรือเปล่า
    """
    tmp = tmp_path_factory.mktemp("serving")
    raw_path = tmp / "observations.parquet"
    model_path = tmp / "model.joblib"

    raw = synthetic.fetch(days=90)
    raw.to_parquet(raw_path, index=False)

    frame = build_features(raw, horizon=HORIZON).dropna(subset=["target", "pm25"])
    columns = feature_columns(frame)

    model = HistGradientBoostingRegressor(max_iter=40, random_state=0)
    model.fit(frame[columns], frame["target"])

    artifact.save(
        {
            "model": model,
            "feature_columns": columns,
            "horizon": HORIZON,
            "trained_at": "2026-01-01T00:00:00+00:00",
            "train_range": ("x", "y"),
            "metrics": {},
        },
        model_path,
    )
    return {"raw_path": raw_path, "model_path": model_path, "raw": raw}


@pytest.fixture(scope="module")
def client(served, monkeypatch_module=None):
    import os

    os.environ["PM25_MODEL_PATH"] = str(served["model_path"])
    os.environ["PM25_RAW_PATH"] = str(served["raw_path"])

    from thaiair.api.app import app

    with TestClient(app) as c:
        yield c

    del os.environ["PM25_MODEL_PATH"]
    del os.environ["PM25_RAW_PATH"]


def test_health_is_alive_regardless(client):
    assert client.get("/health").status_code == 200


def test_ready_reports_model_metadata(client):
    body = client.get("/ready").json()
    assert body["status"] == "ready"
    assert body["horizon_hours"] == HORIZON


def test_predict_returns_a_number_for_the_right_time(client):
    body = client.post("/predict", json={"station_id": STATION}).json()

    based_on = pd.Timestamp(body["based_on"])
    predicted_for = pd.Timestamp(body["predicted_for"])

    # ช่องว่างต้องเท่ากับ horizon เป๊ะ — ไม่งั้นคนใช้จะเข้าใจผิดว่าค่านี้เป็นของเวลาไหน
    assert predicted_for - based_on == pd.Timedelta(hours=HORIZON)
    assert isinstance(body["pm25"], float)


def test_unknown_station_gives_404_not_500(client):
    response = client.post("/predict", json={"station_id": "ไม่มีจริง"})
    assert response.status_code == 404


def test_api_prediction_matches_the_training_path(client, served):
    """⭐ ตัวสำคัญที่สุดของไฟล์นี้ — กัน train/serve skew

    คำนวณค่าทำนายด้วย "เส้นทางเทรน" แล้วเทียบกับที่ API ตอบ
    ถ้าวันหนึ่งมีคนแก้ build_features หรือเปลี่ยนวิธีเลือกคอลัมน์ที่ฝั่งใดฝั่งหนึ่ง
    ตัวเลขสองฝั่งจะเริ่มไม่ตรงกัน — และนี่คือสิ่งเดียวที่จะบอก
    """
    art = artifact.load(served["model_path"])

    frame = build_features(served["raw"], horizon=art["horizon"])
    row = frame[frame["station_id"] == STATION].iloc[[-1]]
    expected = float(art["model"].predict(row[art["feature_columns"]])[0])

    got = client.post("/predict", json={"station_id": STATION}).json()["pm25"]

    assert got == pytest.approx(round(expected, 2), abs=0.01)
