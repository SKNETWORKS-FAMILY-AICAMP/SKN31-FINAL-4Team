class AblyCollectError(Exception):
    """ABLY API 수집 과정에서 발생한 오류."""


class AblyAuthenticationError(AblyCollectError):
    """ABLY 익명 인증 정보가 없거나 유효하지 않을 때 발생하는 오류."""


class AblyParseError(Exception):
    """ABLY API 응답 구조가 예상과 다를 때 발생하는 오류."""
