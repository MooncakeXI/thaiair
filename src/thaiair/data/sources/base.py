"""สัญญาของแหล่งข้อมูล"""

from __future__ import annotations

from typing import Any, Protocol

import pandas as pd


class Source(Protocol):
    """ทุกแหล่งข้อมูลต้องเป็นสิ่งที่เรียกได้แบบนี้

    - รับ `days` เป็น keyword argument
    - คืน DataFrame ที่ผ่าน conform() แล้ว (ดู schema.py)

    หมายเหตุ: Protocol ไม่ตรวจอะไรตอนรัน มันคือเอกสารที่เครื่องอ่านได้
    ตัวที่บังคับสัญญาจริงคือ tests/test_source_contract.py
    """

    def __call__(self, *, days: int = ..., **kwargs: Any) -> pd.DataFrame: ...