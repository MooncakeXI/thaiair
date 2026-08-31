"""เทรนโมเดลแล้วเทียบกับ baseline

    python -m thaiair.models.train

กติกา: ถ้าแพ้ baseline ให้ exit code ไม่เป็น 0
CI ในขั้น 7 จะได้จับได้เองโดยไม่ต้องมีคนมานั่งอ่าน
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from thaiair.features.build import build_features

DEFAULT_RAW = Path("data/raw/observations.parquet")

# คอลัมน์ที่บอกว่า "แถวนี้คือใคร" ไม่ใช่ฟีเจอร์
# station_id เป็นข้อความ ยังไม่ใส่ในรอบนี้ — เก็บไว้ปรับปรุงทีหลัง
NOT_FEATURES = {"timestamp", "station_id", "target"}


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def chronological_split(
    frame: pd.DataFrame, test_fraction: float = 0.2
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """แบ่งที่จุดเวลาหนึ่ง — อดีตไปเทรน อนาคตไปทดสอบ

    ⚠️ ห้ามใช้ train_test_split(shuffle=True) กับ time series เด็ดขาด
    การสุ่มทำให้โมเดลได้เห็นข้อมูลที่ "ยังไม่เกิดขึ้น" ตอนเทรน
    ซึ่งตอน deploy มันไม่มีทางเห็น — คะแนนที่ได้จึงเป็นคะแนนของโลกที่ไม่มีอยู่จริง

    ใช้จุดตัดจาก "เวลาที่ไม่ซ้ำกัน" ไม่ใช่จากจำนวนแถว
    เพราะหนึ่งเวลามีหลายแถว (หลายสถานี) — ตัดตามแถวจะทำให้สถานีหนึ่ง
    มีข้อมูลของช่วงเวลาที่อีกสถานีถูกกันไว้ทดสอบ
    """
    times = np.sort(frame["timestamp"].unique())
    cutoff = times[int(len(times) * (1 - test_fraction))]

    train = frame[frame["timestamp"] < cutoff]
    test = frame[frame["timestamp"] >= cutoff]
    return train, test, pd.Timestamp(cutoff)


def main() -> None:
    parser = argparse.ArgumentParser(description="เทรนโมเดลแล้วเทียบกับ baseline")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument(
        "--min-improvement",
        type=float,
        default=0.0,
        help="ต้องดีกว่า baseline กี่ %% ถึงจะถือว่าผ่าน",
    )
    args = parser.parse_args()

    raw = pd.read_parquet(args.raw)
    frame = build_features(raw, horizon=args.horizon)

    # แถวที่ไม่มีค่าเป้าหมายใช้ไม่ได้ (แถวสุดท้ายของแต่ละสถานี)
    # และแถวที่ไม่มีค่าปัจจุบัน baseline ทำนายไม่ได้ —
    # ต้องตัดออกทั้งคู่เพื่อให้ทั้งสองฝ่ายถูกวัดบน "แถวชุดเดียวกัน"
    frame = frame.dropna(subset=["target", "pm25"])

    train, test, cutoff = chronological_split(frame, args.test_fraction)
    feature_cols = sorted(c for c in frame.columns if c not in NOT_FEATURES)

    y_test = test["target"].to_numpy()

    # ── baseline: ชั่วโมงหน้า = ชั่วโมงนี้ ────────────────────
    baseline_pred = test["pm25"].to_numpy()
    baseline_mae = mae(y_test, baseline_pred)

    # ── โมเดล ────────────────────────────────────────────────
    model = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.05,
        random_state=0,
    )
    model.fit(train[feature_cols], train["target"])
    model_pred = model.predict(test[feature_cols])
    model_mae = mae(y_test, model_pred)

    improvement = (baseline_mae - model_mae) / baseline_mae * 100

    print(f"ช่วงเทรน   : {train.timestamp.min()} → {train.timestamp.max()}  ({len(train):,} แถว)")
    print(f"ช่วงทดสอบ  : {test.timestamp.min()} → {test.timestamp.max()}  ({len(test):,} แถว)")
    print(f"จุดตัด     : {cutoff}")
    print(f"ฟีเจอร์    : {len(feature_cols)} คอลัมน์")
    print()
    print(f"baseline (persistence)  MAE = {baseline_mae:7.3f}   RMSE = {rmse(y_test, baseline_pred):7.3f}")
    print(f"model                   MAE = {model_mae:7.3f}   RMSE = {rmse(y_test, model_pred):7.3f}")
    print()
    print(f"ดีขึ้น {improvement:+.1f}%")

    if improvement < args.min_improvement:
        print(
            f"\n❌ ไม่ผ่าน — ต้องดีกว่า baseline อย่างน้อย {args.min_improvement:.1f}%",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n✅ ผ่าน")


if __name__ == "__main__":
    main()