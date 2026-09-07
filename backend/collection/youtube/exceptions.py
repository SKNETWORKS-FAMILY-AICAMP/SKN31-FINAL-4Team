class YoutubeCollectError(Exception):
    """YouTube API 수집 실패."""


class YoutubeParseError(Exception):
    """YouTube 응답 파싱 실패."""