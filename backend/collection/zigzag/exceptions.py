class ZigzagCollectError(Exception):
    """ZIGZAG 수집 과정에서 발생한 오류."""


# 다른 플랫폼(무신사/크림/유튜브)은 모두 CollectError + ParseError 쌍을 두는데
# 지그재그만 ParseError 가 없어서, parser.py 가 raise 하는 이름이
# 정의되지 않은 상태였다. (2026-09-09 추가)
class ZigzagParseError(Exception):
    """ZIGZAG HTML/JSON 파싱 실패."""
