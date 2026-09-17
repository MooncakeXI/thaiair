"""เทรนโมเดลแล้วเทียบกับ baseline

    python -m thaiair.models.train

กติกา: ถ้าแพ้ baseline ให้ exit code ไม่เป็น 0
CI ในขั้น 7 จะได้จับได้เองโดยไม่ต้องมีคนมานั่งอ่าน
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from thaiair.features.build import build_features
from thaiair.models import artifact

DEFAULT_RAW = Path("data/raw/observations.parquet")

# คอลัมน์ที่บอกว่า "แถวนี้คือใคร" ไม่ใช่ฟีเจอร์
# station_id เป็นข้อความ ยังไม่ใส่ในรอบนี้ — เก็บไว้ปรับปรุงทีหลัง
NOT_FEATURES = {"timestamp", "station_id", "target"}

BURNING_MONTHS = {12, 1, 2, 3, 4}


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


def report_by_season(
    test: pd.DataFrame,
    y_true: np.ndarray,
    baseline_pred: np.ndarray,
    model_pred: np.ndarray,
) -> None:
    """แยกผลตามฤดู — MAE ตัวเดียวกลบความจริงว่าอ่อนตรงไหน

    ถ้าตารางนี้โผล่มาแค่ฤดูเดียว นั่นคือคำเตือนในตัวมันเอง:
    แปลว่าอีกฤดูไม่เคยถูกทดสอบเลย
    """
    sliced = pd.DataFrame(
        {
            "season": np.where(test["timestamp"].dt.month.isin(BURNING_MONTHS), "หน้าเผา", "หน้าฝน"),
            "y": y_true,
            "baseline": baseline_pred,
            "model": model_pred,
        }
    )

    print("\nแยกตามฤดู:")
    for season, group in sliced.groupby("season"):
        b = mae(group["y"].to_numpy(), group["baseline"].to_numpy())
        m = mae(group["y"].to_numpy(), group["model"].to_numpy())

        # ถ้า baseline สมบูรณ์แบบ (b = 0) การเทียบเป็น % หารด้วยศูนย์
        # mae() คืน Python float ไม่ใช่ numpy float → ZeroDivisionError ไม่ใช่ nan
        delta = f"{(b - m) / b * 100:+5.1f}%" if b else "  n/a"

        print(
            f"  {season}  n={len(group):6,}   "
            f"baseline={b:6.3f}   model={m:6.3f}   ดีขึ้น {delta}"
        )


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """คอลัมน์ที่โมเดลใช้ — เรียงแน่นอนทุกครั้ง

    แยกออกมาเพราะเทสต์ต้องใช้ตัวเดียวกับที่เทรนใช้
    ถ้าเทสต์คำนวณเอง มันจะไม่ได้ทดสอบเส้นทางจริง — ซึ่งคือ skew ที่เรากำลังกันอยู่พอดี
    """
    return sorted(c for c in frame.columns if c not in NOT_FEATURES)


def main() -> None:
    parser = argparse.ArgumentParser(description="เทรนโมเดลแล้วเทียบกับ baseline")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--horizon", type=int, default=24)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--out", type=Path, default=artifact.DEFAULT_PATH)
    parser.add_argument("--no-save", action="store_true", help="เทรนเพื่อวัดผลอย่างเดียว ไม่บันทึก")
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

    # 🔴 ด่านสำคัญ: ชุดว่างต้องหยุดที่นี่
    #
    # np.mean([]) คืน nan (แค่ warning ไม่ error) แล้ว improvement จะเป็น nan
    # และ `nan < min_improvement` เป็น False เสมอ — โมเดลที่ไม่ได้ถูกวัดกับข้อมูล
    # สักแถวจะพิมพ์ "ผ่าน" แล้วบันทึกทับตัวเก่า
    #
    # nan ทำให้ guardrail หลุดโดยไม่มีอะไรฟ้อง จึงต้องดักก่อนถึงจุดนั้น
    if train.empty or test.empty:
        print(
            f"❌ แบ่งข้อมูลแล้วเหลือ train={len(train)} test={len(test)} — "
            "ปรับ --test-fraction หรือเช็คว่าข้อมูลดิบมีพอไหม",
            file=sys.stderr,
        )
        sys.exit(1)

    feature_cols = feature_columns(frame)

    y_test = test["target"].to_numpy()

    # ── baseline: ชั่วโมงหน้า = ชั่วโมงนี้ ────────────────────
    baseline_pred = test["pm25"].to_numpy()
    baseline_mae = mae(y_test, baseline_pred)

    if baseline_mae == 0:
        print(
            "❌ baseline MAE = 0 — ข้อมูลทดสอบไม่มีการเปลี่ยนแปลงเลย เทียบเป็น % ไม่ได้",
            file=sys.stderr,
        )
        sys.exit(1)

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

    print(f"ช่วงเทรน   : {train['timestamp'].min()} → {train['timestamp'].max()}  ({len(train):,} แถว)")
    print(f"ช่วงทดสอบ  : {test['timestamp'].min()} → {test['timestamp'].max()}  ({len(test):,} แถว)")
    print(f"จุดตัด     : {cutoff}")
    print(f"ฟีเจอร์    : {len(feature_cols)} คอลัมน์")
    print()
    print(
        f"baseline (persistence)  MAE = {baseline_mae:7.3f}   RMSE = {rmse(y_test, baseline_pred):7.3f}"
    )
    print(
        f"model                   MAE = {model_mae:7.3f}   RMSE = {rmse(y_test, model_pred):7.3f}"
    )
    print()
    print(f"ดีขึ้น {improvement:+.1f}%")

    report_by_season(test, y_test, baseline_pred, model_pred)

    if improvement < args.min_improvement:
        print(
            f"\n❌ ไม่ผ่าน — ต้องดีกว่า baseline อย่างน้อย {args.min_improvement:.1f}%",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n✅ ผ่าน")

    if args.no_save:
        return

    saved = artifact.save(
        {
            "model": model,
            "feature_columns": feature_cols,
            "horizon": args.horizon,
            "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "train_range": (str(train["timestamp"].min()), str(train["timestamp"].max())),
            "metrics": {
                "baseline_mae": baseline_mae,
                "model_mae": model_mae,
                "improvement_pct": improvement,
            },
        },
        args.out,
    )
    print(f"บันทึกโมเดล → {saved}")


if __name__ == "__main__":
    main()
