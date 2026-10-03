"""서버 시작 경로 회귀 테스트 (2026-09-18).

engine() 이 llm.DISABLED 를 쓰는데 server.py 맨 위에서 llm 을 import 하지 않아,
배포 컨테이너가 NameError 로 재시작을 반복했다(nginx 502 → 사이트는 데모 답).
import 만 확인하던 검사로는 안 잡혔다 — engine() 을 실제로 부르는 줄까지 본다.
"""
import unittest
import server


class ServerBootTests(unittest.TestCase):
    def test_engine_uses_names_defined_at_module_level(self):
        # engine() 안에서 쓰는 전역 이름이 모두 모듈에 있어야 한다
        names = server.engine.__code__.co_names
        missing = [n for n in names if n not in vars(server) and n not in dir(__builtins__)
                   and n not in ("DISABLED",)]
        assert missing == [], missing
        assert hasattr(server.llm, "DISABLED")


    def test_rds_numeric_becomes_plain_numbers(self):
        """Postgres numeric(Decimal) 가 리포트에 섞여 json 이 죽던 문제 (2026-09-18)."""
        from decimal import Decimal
        from app.rds_store import _plain
        assert _plain(Decimal("82")) == 82 and isinstance(_plain(Decimal("82")), int)
        assert _plain(Decimal("0.62")) == 0.62
        assert _plain([Decimal("1.5"), "x"]) == [1.5, "x"]


    def test_sse_survives_decimal_and_dates(self):
        import datetime
        from decimal import Decimal
        out = server.sse("report", {"rate": Decimal("0.62"), "at": datetime.date(2026, 9, 8)})
        assert b'"rate": 0.62' in out and b'"2026-09-08"' in out
