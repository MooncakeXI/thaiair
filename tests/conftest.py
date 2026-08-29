"""ตั้งค่าที่ใช้ร่วมกันทุกเทสต์"""

from __future__ import annotations

import httpx
import pytest


@pytest.fixture(autouse=True)
def block_real_network(request: pytest.FixtureRequest, monkeypatch):
    """ห้ามเทสต์ต่อเน็ตจริง เว้นแต่จะติดป้าย @pytest.mark.live

    ทำไมต้องมี: การเดินสาย MockTransport ให้ครบทุกแหล่ง เป็นเรื่องที่ "ลืมได้"
    วันที่คุณเพิ่ม openaq แล้วลืมใส่ mock เทสต์จะยังเขียว แค่ช้าลงและ
    พังเป็นครั้งคราวตอนเน็ตสะดุด — ซึ่งเป็นอาการที่ตามหาต้นตอยากมาก

    บรรทัดล่างทำให้ "ลืม" กลายเป็นเทสต์แดงทันที
    MockTransport ไม่ผ่านทางนี้ ของที่ mock ไว้จึงยังทำงานปกติ
    """
    if "live" in request.keywords:
        return

    def deny(*args, **kwargs):
        raise RuntimeError(
            "เทสต์พยายามต่อเน็ตจริง — ต้องส่ง httpx.MockTransport เข้าไป "
            "หรือติดป้าย @pytest.mark.live ถ้าตั้งใจให้ยิงจริง"
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny)