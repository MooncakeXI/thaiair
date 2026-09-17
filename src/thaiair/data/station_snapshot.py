from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from thaiair.data.sources import openaq

DEFAULT_OUT = Path("data/raw/stations.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="บันทึกชื่อและพิกัดสถานี OpenAQ")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "stations": openaq.discover(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"เขียน {len(payload['stations'])} สถานี → {args.out}")


if __name__ == "__main__":
    main()
