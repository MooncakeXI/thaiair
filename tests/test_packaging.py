from importlib.metadata import version

import thaiair


def test_installed_version_matches_source():
    """เวอร์ชันที่ pip ติดตั้งไว้ ต้องตรงกับที่เขียนใน __init__.py

    เทสต์นี้ไม่ได้ทดสอบตรรกะอะไรเลย แต่ทดสอบว่า "การแพ็กเกจ" ของเราถูก —
    ซึ่งเป็นสิ่งที่พังแบบเงียบที่สุด
    """
    assert version("thaiair") == thaiair.__version__