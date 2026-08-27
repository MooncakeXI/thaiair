from __future__ import annotations

import argparse
from pathlib import Path

from thaiair.data.sources import SOURCES

DEFAULT_OUT = Path("data/raw/observations.parquet")


def main() -> None:
    parser = argparse.ArgumentParser(description="ดึงข้อมูลตรวจวัดลงดิสก์")
    parser.add_argument("--source", choices=sorted(SOURCES), default="synthetic")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    df = SOURCES[args.source](days=args.days)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)

    print(f"เขียน {len(df):,} แถว → {args.out}")
    print(f"ช่วงเวลา (UTC) : {df.timestamp.min()} → {df.timestamp.max()}")
    print(f"สถานี          : {df.station_id.nunique()}")
    print(f"พารามิเตอร์     : {sorted(df.parameter.unique())}")
    print(f"ค่าที่หายไป      : {df.value.isna().sum():,} ({df.value.isna().mean():.1%})")


if __name__ == "__main__":
    main()