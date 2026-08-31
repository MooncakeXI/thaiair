"""ชั้น HTTP — รู้จักการยิงเน็ตให้ทน แต่ไม่รู้จัก PM2.5

ที่แยกออกมาเพราะสองเหตุผล:
1. วันที่ API เปลี่ยนรูป JSON แก้ที่ชั้น parse ที่เดียว ไม่ต้องแตะ retry
2. เทสต์ชั้น parse ได้โดยไม่ต้องต่อเน็ต — ซึ่งเป็นเหตุผลที่หนักกว่า
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

# status ที่ "ลองใหม่แล้วมีโอกาสสำเร็จ" — ปัญหาชั่วคราวฝั่งเซิร์ฟเวอร์
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

# 401 = key ผิด · 404 = ไม่มีของ · 400 = เราส่งผิด
# พวกนี้ retry ไปกี่รอบก็ได้คำตอบเดิม แค่ทำให้ช้าลงและกวนเซิร์ฟเวอร์เขาเปล่าๆ

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_ATTEMPTS = 5
BASE_DELAY = 1.0
MAX_DELAY = 30.0


def _sleep_seconds(attempt: int, retry_after: str | None) -> float:
    """คำนวณว่าจะรอกี่วินาทีก่อนลองใหม่

    เซิร์ฟเวอร์บอกเองดีที่สุด — ถ้ามี Retry-After ให้เชื่อเขา
    ไม่มีก็ถอยแบบทวีคูณ: 1, 2, 4, 8, 16 วินาที
    """
    if retry_after:
        try:
            return min(float(retry_after), MAX_DELAY)
        except ValueError:
            pass  # บาง API ส่งมาเป็นวันที่แทนตัวเลข — ไม่เป็นไร ถอยเองแทน

    delay = min(BASE_DELAY * (2**attempt), MAX_DELAY)

    # ⬇️ jitter — สำคัญกว่าที่หน้าตามันบอก
    # ถ้าไคลเอนต์ 100 ตัวเจอ 503 พร้อมกันแล้วรอ 2 วินาทีเท่ากันหมด
    # มันจะกลับมาถล่มเซิร์ฟเวอร์พร้อมกันอีกรอบตอนที่เขากำลังจะฟื้น
    # สุ่มกระจายเวลาออก แล้วโหลดจะเกลี่ยตัวเอง
    return delay * (0.5 + random.random())


def get_json(
    url: str,
    params: dict[str, Any],
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """ยิง GET แล้วคืน JSON — ลองใหม่เมื่อเจอปัญหาชั่วคราว

    `client` มีไว้ให้เทสต์ส่ง httpx.MockTransport เข้ามา
    โค้ดจริงไม่ต้องส่ง เดี๋ยวสร้างเองแล้วปิดให้
    """
    owns_client = client is None
    client = client or httpx.Client(timeout=DEFAULT_TIMEOUT)

    try:
        last_error: Exception | None = None

        for attempt in range(MAX_ATTEMPTS):
            try:
                response = client.get(url, params=params)

                if response.status_code in RETRYABLE_STATUS:
                    wait = _sleep_seconds(attempt, response.headers.get("Retry-After"))
                    log.warning(
                        "got %s from %s, retrying in %.1fs (attempt %d/%d)",
                        response.status_code,
                        url,
                        wait,
                        attempt + 1,
                        MAX_ATTEMPTS,
                    )
                    last_error = httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    time.sleep(wait)
                    continue

                # status อื่นที่ไม่ใช่ 2xx — โยนทันที ไม่ต้องลองใหม่
                response.raise_for_status()
                return response.json()

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                # เน็ตสะดุด/DNS ล่ม — ประเภทเดียวกับ 503 คือลองใหม่คุ้ม
                last_error = exc
                wait = _sleep_seconds(attempt, None)
                log.warning("network error: %s, retrying in %.1fs", exc, wait)
                time.sleep(wait)

        raise RuntimeError(f"ยิง {url} ไม่สำเร็จหลังลอง {MAX_ATTEMPTS} ครั้ง") from last_error

    finally:
        # ปิดเฉพาะ client ที่เราสร้างเอง — ของที่คนอื่นส่งมาให้ เขาปิดเอง
        if owns_client:
            client.close()
