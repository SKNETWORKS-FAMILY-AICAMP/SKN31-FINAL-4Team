YOUTUBE_API_BASE_URL = (
    "https://www.googleapis.com/youtube/v3"
)

CHANNELS_API_URL = (
    f"{YOUTUBE_API_BASE_URL}/channels"
)

SOURCE_CODE = "YOUTUBE"

PROFILE_TYPE = "YOUTUBE_CHANNEL"

REQUEST_TIMEOUT = 20


# ============================================================
# VIDEO
# ============================================================

PLAYLIST_ITEMS_API_URL = (
    f"{YOUTUBE_API_BASE_URL}/playlistItems"
)

VIDEOS_API_URL = (
    f"{YOUTUBE_API_BASE_URL}/videos"
)

WATCH_URL = (
    "https://www.youtube.com/watch?v={video_id}"
)

# 채널당 기본 수집 영상 수
DEFAULT_VIDEO_LIMIT = 50

# playlistItems / videos 모두 1회 최대 50건
API_PAGE_SIZE = 50

# 이 길이 이하이면 SHORTS로 분류한다.
# YouTube API가 쇼츠 여부를 알려주지 않으므로 길이로 추정한다.
#
# 180초 = YouTube가 2024년 10월부터 적용한 쇼츠 최대 길이.
# 실제 수집 데이터에서도 181~300초 구간이 비어 있어
# 쇼츠(<=180s)와 일반 영상(300s+)이 명확히 갈렸다.
#
# duration_seconds 원본을 그대로 저장하므로
# 기준이 바뀌어도 재수집 없이 재분류할 수 있다.
SHORTS_MAX_SECONDS = 180

VIDEO_PARTS = (
    "snippet,"
    "statistics,"
    "contentDetails,"
    "status"
)


# ============================================================
# COMMENT
# ============================================================

COMMENT_THREADS_API_URL = (
    f"{YOUTUBE_API_BASE_URL}/commentThreads"
)

# commentThreads는 1회 최대 100건.
# 요청 1건당 1 unit이므로 영상당 1페이지만 받는다.
COMMENT_PAGE_SIZE = 100

DEFAULT_COMMENT_LIMIT = 100

# relevance = YouTube가 판단한 인기 댓글 순.
COMMENT_ORDER = "relevance"

COMMENT_PARTS = "snippet,replies"
