"""ทะเบียนแหล่งข้อมูล

เพิ่มแหล่งใหม่ = เพิ่มบรรทัดเดียวในนี้ แล้วเทสต์สัญญาจะครอบคลุมมันทันที
โดยไม่ต้องไปเขียนเทสต์เพิ่มเลย
"""

from thaiair.data.sources import openaq, openmeteo, synthetic
from thaiair.data.sources.base import Source

SOURCES: dict[str, Source] = {
    "synthetic": synthetic.fetch,
    "openmeteo": openmeteo.fetch,
    "openaq": openaq.fetch,
}

__all__ = ["SOURCES", "Source"]
