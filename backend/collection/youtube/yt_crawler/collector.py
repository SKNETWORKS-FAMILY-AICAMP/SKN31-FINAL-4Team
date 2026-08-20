"""
FEEDIT YouTube Creator Collector v5

목표
- 한국 패션 크리에이터 남/여 10명씩, 총 20개 채널을 중심으로 최근 영상을 수집
- 최초 1회만 채널명을 YouTube search.list로 확인하고, 이후 channel_id를 캐시해 검색 호출 절약
- 각 채널의 uploads playlist에서 최신 영상을 가져오기 때문에 키워드 전체 검색보다 노이즈를 줄임
- 영상 메타데이터, 조회수, 좋아요, 댓글 수, 채널 통계, 공개 댓글/댓글 좋아요, 자막을 JSON/JSONL로 저장
- .env의 YOUTUBE_API_KEY 사용
- DB 적재를 고려해 영상 단위 통합 JSONL(video_documents.jsonl) 생성

주의
- youtube-transcript-api는 YouTube Data API 공식 자막 API가 아닌 외부 라이브러리입니다.
  영상/지역/네트워크 상황에 따라 자막 수집에 실패할 수 있으며 실패는 JSON에 기록하고 계속 진행합니다.
- 댓글 작성자 정보는 기본적으로 저장하지 않습니다.
- 채널 자동 매칭이 잘못될 수 있으므로 첫 실행 뒤 data/youtube/creator_channels_resolved.json을 확인하세요.
  creator_channels.json에 channel_id 또는 handle을 직접 넣으면 자동 검색보다 정확합니다.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


# ============================================================
# 1. 환경 / 설정
# ============================================================

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
REGION_CODE = "KR"
RELEVANCE_LANGUAGE = "ko"

# YouTube 기본 한도보다 여유 있게 설정
DAILY_SEARCH_CALL_LIMIT = int(os.getenv("FEEDIT_DAILY_SEARCH_LIMIT", "80"))
DAILY_GENERAL_UNIT_LIMIT = int(os.getenv("FEEDIT_DAILY_GENERAL_LIMIT", "8000"))

DEFAULT_DAYS_BACK = 30
DEFAULT_VIDEOS_PER_CREATOR = 10
DEFAULT_COMMENT_PAGES_PER_VIDEO = 1
DEFAULT_TRANSCRIPT_SLEEP_SEC = 3.0
DEFAULT_TRANSCRIPT_BATCH_SIZE = 50
DEFAULT_TRANSCRIPT_COOLDOWN_RANGE = (30.0, 60.0)
DEFAULT_TRANSCRIPT_MAX_RETRIES = 3
DEFAULT_TRANSCRIPT_BASE_BACKOFF_SEC = 2.0


PROJECT_DIR = Path(__file__).resolve().parent.parent
V5_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = Path(
    os.getenv("FEEDIT_YOUTUBE_OUTPUT_DIR", str(PROJECT_DIR / "data" / "youtube"))
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = OUTPUT_DIR / "feedit_youtube.db"

CREATOR_CONFIG_PATH = Path(os.getenv("FEEDIT_CREATOR_CONFIG_PATH", str(V5_DIR / "creator_channels.json")))
RESOLVED_CREATORS_JSON = OUTPUT_DIR / "creator_channels_resolved.json"
CREATORS_CURRENT_JSON = OUTPUT_DIR / "creators_current.json"
CREATOR_VIDEO_MATCHES_JSON = OUTPUT_DIR / "creator_video_matches.json"
VIDEOS_JSON = OUTPUT_DIR / "videos_current.json"
CHANNELS_JSON = OUTPUT_DIR / "channels_current.json"
COMMENTS_JSON = OUTPUT_DIR / "comments_current.json"
TRANSCRIPTS_JSON = OUTPUT_DIR / "transcripts_current.json"
VIDEO_SNAPSHOTS_JSONL = OUTPUT_DIR / "video_snapshots.jsonl"
CHANNEL_SNAPSHOTS_JSONL = OUTPUT_DIR / "channel_snapshots.jsonl"
COMMENT_SNAPSHOTS_JSONL = OUTPUT_DIR / "comment_snapshots.jsonl"
VIDEO_DOCUMENTS_JSONL = OUTPUT_DIR / "video_documents.jsonl"
DAILY_BUNDLE_JSON = OUTPUT_DIR / "feedit_youtube_daily_bundle.json"
QUOTA_JSON = OUTPUT_DIR / "quota_usage.json"

# 채널 영상 중 패션 관련 영상 판단용. 전용 패션 채널은 config에서 fashion_filter=false로 바꿀 수 있습니다.
FASHION_KEYWORDS = [
    "패션", "코디", "룩북", "하울", "옷", "스타일", "스타일링", "트렌드", "착장", "데일리룩", "ootd",
    "상의", "하의", "아우터", "자켓", "재킷", "블레이저", "코트", "패딩", "블루종", "바람막이", "점퍼",
    "셔츠", "티셔츠", "니트", "후드", "맨투맨", "가디건", "블라우스", "팬츠", "바지", "데님", "슬랙스",
    "스커트", "쇼츠", "핏", "실루엣", "와이드", "오버핏", "크롭", "레귤러", "슬림",
    "스웨이드", "레더", "가죽", "울", "트위드", "데님", "코튼", "린넨", "나일론",
    "브랜드", "쇼핑", "구매", "신상", "시즌", "ss", "fw", "f/w", "s/s",
]

DEFAULT_CREATORS: List[Dict[str, Any]] = [
    # 남성 10
    {"name": "깡스타일리스트", "gender": "남성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "핏더사이즈", "gender": "남성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "스타일가이드 최겨울", "gender": "남성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "오늘의 주우재", "gender": "남성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "짱구대디", "gender": "남성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "패션튜브삭형", "gender": "남성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "fashion piro", "gender": "남성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "미누의코디", "gender": "남성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "호수", "gender": "남성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "스토커즈 STalkers", "gender": "남성", "channel_id": "", "handle": "", "fashion_filter": True},
    # 여성 10
    {"name": "옆집언니 최실장", "gender": "여성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "AliceFunk 앨리스펑크", "gender": "여성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "보라끌레르 Bora Claire", "gender": "여성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "소신사장 SoshinTV", "gender": "여성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "혜인 HEYNEE", "gender": "여성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "에이프롬 ÁFROM", "gender": "여성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "박에스더", "gender": "여성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "samedifference", "gender": "여성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "메리지히 MerryJihee", "gender": "여성", "channel_id": "", "handle": "", "fashion_filter": True},
    {"name": "물결 Mulgyul", "gender": "여성", "channel_id": "", "handle": "", "fashion_filter": True},
]


# ============================================================
# 2. 유틸
# ============================================================


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def chunks(values: Sequence[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(values), size):
        yield list(values[i : i + size])


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item") and not isinstance(value, (str, bytes, dict, list, tuple)):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    return value


def dataframe_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    return [{str(k): json_safe(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def jsonl_dumps(record: Dict[str, Any]) -> str:
    """Serialize one JSONL record without embedded Unicode line separators."""
    serialized = json.dumps(json_safe(record), ensure_ascii=False)
    for character, escaped in {
        "\x1c": "\\u001c",
        "\x1d": "\\u001d",
        "\x1e": "\\u001e",
        "\x85": "\\u0085",
        "\u2028": "\\u2028",
        "\u2029": "\\u2029",
    }.items():
        serialized = serialized.replace(character, escaped)
    return serialized


def write_json_records(records: Sequence[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([json_safe(x) for x in records], ensure_ascii=False, indent=2), encoding="utf-8")


def write_json_df(df: pd.DataFrame, path: Path) -> None:
    write_json_records(dataframe_records(df), path)


def read_json_records(path: Path) -> List[Dict[str, Any]]:
    """Return a JSON array as records, treating a missing file as empty."""
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}") from exc
    return [record for record in value if isinstance(record, dict)] if isinstance(value, list) else []


def merge_json_records(
    records: Sequence[Dict[str, Any]], path: Path, key_fields: Sequence[str]
) -> None:
    """Add or update records by key without discarding prior collection output."""
    merged: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for record in [*read_json_records(path), *records]:
        key = tuple(str(record.get(field, "")) for field in key_fields)
        if all(key):
            merged[key] = dict(record)
    write_json_records(list(merged.values()), path)


def load_known_video_ids() -> set[str]:
    """Load previously stored video IDs from SQLite and collector JSON output."""
    known: set[str] = set()
    if DATABASE_PATH.exists():
        try:
            with sqlite3.connect(DATABASE_PATH) as connection:
                columns = connection.execute('PRAGMA table_info("videos")').fetchall()
                if any(column[1] == "video_id" for column in columns):
                    known.update(
                        str(row[0])
                        for row in connection.execute(
                            'SELECT "video_id" FROM "videos" WHERE "video_id" IS NOT NULL'
                        )
                    )
        except sqlite3.Error as exc:
            print(f"[WARN] Could not read existing video IDs from DB: {exc}")

    known.update(
        str(record["video_id"])
        for record in read_json_records(VIDEOS_JSON)
        if record.get("video_id")
    )
    return known


def append_jsonl_records(records: Sequence[Dict[str, Any]], path: Path) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(jsonl_dumps(record) + "\n")


def append_jsonl_df(df: pd.DataFrame, path: Path) -> None:
    append_jsonl_records(dataframe_records(df), path)


def ensure_creator_config() -> None:
    if CREATOR_CONFIG_PATH.exists():
        return
    CREATOR_CONFIG_PATH.write_text(json.dumps(DEFAULT_CREATORS, ensure_ascii=False, indent=2), encoding="utf-8")


def load_creator_config() -> List[Dict[str, Any]]:
    ensure_creator_config()
    data = json.loads(CREATOR_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("creator_channels.json은 JSON 배열이어야 합니다.")
    return data


def is_fashion_relevant(video: Dict[str, Any]) -> bool:
    text = " ".join([
        str(video.get("title", "")),
        str(video.get("description", "")),
        " ".join(video.get("tags", []) or []),
    ]).lower()
    return any(keyword.lower() in text for keyword in FASHION_KEYWORDS)


# ============================================================
# 3. 쿼터 가드
# ============================================================


@dataclass
class QuotaGuard:
    search_calls: int = 0
    general_units: int = 0
    search_limit: int = DAILY_SEARCH_CALL_LIMIT
    general_limit: int = DAILY_GENERAL_UNIT_LIMIT

    def can_search(self, cost: int = 1) -> bool:
        return self.search_calls + cost <= self.search_limit

    def can_general(self, cost: int = 1) -> bool:
        return self.general_units + cost <= self.general_limit

    def use_search(self, cost: int = 1) -> None:
        if not self.can_search(cost):
            raise RuntimeError("SEARCH_DAILY_LIMIT_REACHED")
        self.search_calls += cost

    def use_general(self, cost: int = 1) -> None:
        if not self.can_general(cost):
            raise RuntimeError("GENERAL_DAILY_LIMIT_REACHED")
        self.general_units += cost

    def save(self) -> None:
        QUOTA_JSON.write_text(
            json.dumps(
                {
                    "saved_at": utc_now_iso(),
                    "search_calls_used": self.search_calls,
                    "search_calls_hard_limit": self.search_limit,
                    "general_units_used": self.general_units,
                    "general_units_hard_limit": self.general_limit,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


# ============================================================
# 4. YouTube API
# ============================================================


class YouTubeCollector:
    def __init__(self, api_key: str, quota: QuotaGuard):
        if not api_key:
            raise RuntimeError(".env에 YOUTUBE_API_KEY를 설정하세요.")
        self.youtube = build("youtube", "v3", developerKey=api_key)
        self.quota = quota

    def _channels_by_ids(self, channel_ids: Sequence[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        ids = list(dict.fromkeys([x for x in channel_ids if x]))
        for batch in chunks(ids, 50):
            if not self.quota.can_general(1):
                break
            self.quota.use_general(1)
            try:
                resp = self.youtube.channels().list(
                    part="snippet,statistics,contentDetails",
                    id=",".join(batch),
                ).execute()
            except HttpError as e:
                print(f"[CHANNELS ERROR] {e}")
                continue
            out.extend(self._parse_channels(resp.get("items", [])))
        return out

    @staticmethod
    def _parse_channels(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in items:
            s = item.get("snippet", {})
            st = item.get("statistics", {})
            cd = item.get("contentDetails", {})
            thumbs = s.get("thumbnails", {})
            rows.append(
                {
                    "channel_id": item.get("id", ""),
                    "channel_title": s.get("title", ""),
                    "channel_description": s.get("description", ""),
                    "custom_url": s.get("customUrl", ""),
                    "channel_published_at": s.get("publishedAt", ""),
                    "country": s.get("country", ""),
                    "channel_thumbnail_high": thumbs.get("high", {}).get("url", ""),
                    "channel_view_count": safe_int(st.get("viewCount")),
                    "subscriber_count": safe_int(st.get("subscriberCount")),
                    "hidden_subscriber_count": bool(st.get("hiddenSubscriberCount", False)),
                    "channel_video_count": safe_int(st.get("videoCount")),
                    "uploads_playlist_id": cd.get("relatedPlaylists", {}).get("uploads", ""),
                    "collected_at": utc_now_iso(),
                }
            )
        return rows

    def channel_by_handle(self, handle: str) -> Optional[Dict[str, Any]]:
        handle = (handle or "").strip()
        if not handle:
            return None
        if not self.quota.can_general(1):
            return None
        self.quota.use_general(1)
        try:
            resp = self.youtube.channels().list(
                part="snippet,statistics,contentDetails",
                forHandle=handle,
            ).execute()
        except HttpError as e:
            print(f"[HANDLE ERROR] {handle}: {e}")
            return None
        rows = self._parse_channels(resp.get("items", []))
        return rows[0] if rows else None

    def resolve_channel_name(self, creator_name: str) -> Optional[Dict[str, Any]]:
        """최초 1회 채널명 검색. 후보 5개 중 제목 유사도 + 구독자 수로 선택."""
        if not self.quota.can_search(1):
            return None
        self.quota.use_search(1)
        try:
            resp = self.youtube.search().list(
                part="snippet",
                q=creator_name,
                type="channel",
                maxResults=5,
                regionCode=REGION_CODE,
                relevanceLanguage=RELEVANCE_LANGUAGE,
                safeSearch="none",
            ).execute()
        except HttpError as e:
            print(f"[CHANNEL SEARCH ERROR] {creator_name}: {e}")
            return None

        candidate_ids = [x.get("id", {}).get("channelId", "") for x in resp.get("items", [])]
        candidates = self._channels_by_ids(candidate_ids)
        if not candidates:
            return None

        q = normalize_text(creator_name)
        q_compact = re.sub(r"[^0-9a-z가-힣]", "", q)

        def score(c: Dict[str, Any]) -> float:
            title = normalize_text(c.get("channel_title", ""))
            compact = re.sub(r"[^0-9a-z가-힣]", "", title)
            exact = 1000 if title == q or compact == q_compact else 0
            contain = 300 if q in title or title in q else 0
            compact_contain = 200 if q_compact and (q_compact in compact or compact in q_compact) else 0
            subs = math.log10(max(1, safe_int(c.get("subscriber_count")))) * 10
            return exact + contain + compact_contain + subs

        return max(candidates, key=score)

    def get_current_channels(self, channel_ids: Sequence[str]) -> List[Dict[str, Any]]:
        return self._channels_by_ids(channel_ids)

    def uploads_playlist_items(
        self,
        playlist_id: str,
        creator_name: str,
        gender: str,
        days_back: int,
        max_videos: int,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not playlist_id:
            return rows
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        page_token: Optional[str] = None
        stop_due_to_age = False

        while len(rows) < max_videos and not stop_due_to_age:
            if not self.quota.can_general(1):
                break
            self.quota.use_general(1)
            try:
                resp = self.youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=min(50, max_videos - len(rows)),
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                print(f"[PLAYLIST ERROR] {creator_name}: {e}")
                break

            for item in resp.get("items", []):
                snippet = item.get("snippet", {})
                content = item.get("contentDetails", {})
                video_id = content.get("videoId") or snippet.get("resourceId", {}).get("videoId")
                published_at = content.get("videoPublishedAt") or snippet.get("publishedAt", "")
                published_dt = parse_datetime(published_at)
                if published_dt and published_dt < cutoff:
                    stop_due_to_age = True
                    break
                if not video_id:
                    continue
                rows.append(
                    {
                        "video_id": video_id,
                        "creator_name": creator_name,
                        "gender_context": gender,
                        "channel_id": snippet.get("channelId", ""),
                        "playlist_id": playlist_id,
                        "playlist_position": safe_int(snippet.get("position")),
                        "playlist_title": snippet.get("title", ""),
                        "playlist_published_at": published_at,
                        "collected_at": utc_now_iso(),
                    }
                )
                if len(rows) >= max_videos:
                    break

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return rows

    def video_details(self, video_ids: Sequence[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        ids = list(dict.fromkeys([x for x in video_ids if x]))
        for batch in chunks(ids, 50):
            if not self.quota.can_general(1):
                break
            self.quota.use_general(1)
            try:
                resp = self.youtube.videos().list(
                    part="snippet,statistics,contentDetails,status,topicDetails",
                    id=",".join(batch),
                ).execute()
            except HttpError as e:
                print(f"[VIDEOS ERROR] {e}")
                continue

            for item in resp.get("items", []):
                s = item.get("snippet", {})
                st = item.get("statistics", {})
                cd = item.get("contentDetails", {})
                status = item.get("status", {})
                topics = item.get("topicDetails", {})
                thumbs = s.get("thumbnails", {})
                vid = item.get("id", "")
                out.append(
                    {
                        "video_id": vid,
                        "video_url": f"https://www.youtube.com/watch?v={vid}",
                        "embed_url": f"https://www.youtube.com/embed/{vid}",
                        "title": s.get("title", ""),
                        "description": s.get("description", ""),
                        "tags": s.get("tags", []),
                        "youtube_category_id": s.get("categoryId", ""),
                        "channel_id": s.get("channelId", ""),
                        "channel_title": s.get("channelTitle", ""),
                        "published_at": s.get("publishedAt", ""),
                        "default_language": s.get("defaultLanguage", ""),
                        "default_audio_language": s.get("defaultAudioLanguage", ""),
                        "thumbnail_default": thumbs.get("default", {}).get("url", ""),
                        "thumbnail_medium": thumbs.get("medium", {}).get("url", ""),
                        "thumbnail_high": thumbs.get("high", {}).get("url", ""),
                        "thumbnail_standard": thumbs.get("standard", {}).get("url", ""),
                        "thumbnail_maxres": thumbs.get("maxres", {}).get("url", ""),
                        "duration_iso8601": cd.get("duration", ""),
                        "caption_available": cd.get("caption", "false"),
                        "definition": cd.get("definition", ""),
                        "licensed_content": cd.get("licensedContent", False),
                        "view_count": safe_int(st.get("viewCount")),
                        "like_count": safe_int(st.get("likeCount")),
                        "comment_count": safe_int(st.get("commentCount")),
                        "privacy_status": status.get("privacyStatus", ""),
                        "embeddable": status.get("embeddable", None),
                        "topic_categories": topics.get("topicCategories", []),
                        "collected_at": utc_now_iso(),
                    }
                )
        return out

    def comment_threads(self, video_id: str, pages: int = 1, include_authors: bool = False) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        for _ in range(max(1, pages)):
            if not self.quota.can_general(1):
                break
            self.quota.use_general(1)
            try:
                resp = self.youtube.commentThreads().list(
                    part="snippet,replies",
                    videoId=video_id,
                    maxResults=100,
                    order="relevance",
                    textFormat="plainText",
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                print(f"[COMMENTS SKIP] {video_id}: {e}")
                break

            for thread in resp.get("items", []):
                ts = thread.get("snippet", {})
                top = ts.get("topLevelComment", {})
                cs = top.get("snippet", {})
                author_channel = cs.get("authorChannelId", {}) or {}
                base = {
                    "video_id": video_id,
                    "comment_thread_id": thread.get("id", ""),
                    "comment_id": top.get("id", ""),
                    "parent_id": "",
                    "is_reply": False,
                    "text": cs.get("textOriginal", cs.get("textDisplay", "")),
                    "like_count": safe_int(cs.get("likeCount")),
                    "published_at": cs.get("publishedAt", ""),
                    "updated_at": cs.get("updatedAt", ""),
                    "total_reply_count": safe_int(ts.get("totalReplyCount")),
                    "collected_at": utc_now_iso(),
                }
                if include_authors:
                    base["author_display_name"] = cs.get("authorDisplayName", "")
                    base["author_channel_id"] = author_channel.get("value", "")
                rows.append(base)

                for reply in thread.get("replies", {}).get("comments", []):
                    rs = reply.get("snippet", {})
                    r_author_channel = rs.get("authorChannelId", {}) or {}
                    row = {
                        "video_id": video_id,
                        "comment_thread_id": thread.get("id", ""),
                        "comment_id": reply.get("id", ""),
                        "parent_id": rs.get("parentId", top.get("id", "")),
                        "is_reply": True,
                        "text": rs.get("textOriginal", rs.get("textDisplay", "")),
                        "like_count": safe_int(rs.get("likeCount")),
                        "published_at": rs.get("publishedAt", ""),
                        "updated_at": rs.get("updatedAt", ""),
                        "total_reply_count": 0,
                        "collected_at": utc_now_iso(),
                    }
                    if include_authors:
                        row["author_display_name"] = rs.get("authorDisplayName", "")
                        row["author_channel_id"] = r_author_channel.get("value", "")
                    rows.append(row)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return rows


# ============================================================
# 5. 자막
# ============================================================


class TranscriptCollector:
    def __init__(
        self,
        languages: Optional[List[str]] = None,
        max_retries: int = DEFAULT_TRANSCRIPT_MAX_RETRIES,
        base_backoff_sec: float = DEFAULT_TRANSCRIPT_BASE_BACKOFF_SEC,
    ):
        self.languages = languages or ["ko", "en"]
        self.api = build_transcript_api()
        self.max_retries = max(1, max_retries)
        self.base_backoff_sec = max(0.0, base_backoff_sec)

    def fetch(self, video_id: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        for attempt in range(1, self.max_retries + 1):
            try:
                fetched = self.api.fetch(video_id, languages=self.languages)
                raw = fetched.to_raw_data()
                language_code = getattr(fetched, "language_code", "")
                is_generated = bool(getattr(fetched, "is_generated", False))
                doc = {
                    "video_id": video_id,
                    "language": getattr(fetched, "language", ""),
                    "language_code": language_code,
                    "is_generated": is_generated,
                    "segment_count": len(raw),
                    "full_text": " ".join(str(x.get("text", "")) for x in raw).strip(),
                    "collected_at": utc_now_iso(),
                    "transcript_status": "success",
                    "error": "",
                }
                segments = [
                    {
                        "video_id": video_id,
                        "segment_index": i,
                        "start_sec": float(x.get("start", 0.0)),
                        "duration_sec": float(x.get("duration", 0.0)),
                        "text": x.get("text", ""),
                        "language_code": language_code,
                        "is_generated": is_generated,
                        "collected_at": utc_now_iso(),
                    }
                    for i, x in enumerate(raw)
                ]
                return doc, segments
            except (TranscriptsDisabled, NoTranscriptFound) as exc:
                logging.info("[%s] 자막이 없거나 비활성화되어 건너뜁니다.", video_id)
                return self._no_transcript_result(video_id, exc)
            except Exception as exc:
                if self._is_request_blocked(exc):
                    raise TranscriptCollectionBlocked(video_id, exc) from exc
                if attempt == self.max_retries:
                    logging.error("[%s] 자막 수집 재시도 %s회 후 실패: %s", video_id, attempt, exc)
                    return self._failed_result(video_id, exc)
                wait_time = self.base_backoff_sec * (2 ** (attempt - 1)) + random.uniform(0.5, 1.5)
                logging.warning(
                    "[%s] 자막 수집 오류(%s). %.1f초 후 재시도 (%s/%s)",
                    video_id, type(exc).__name__, wait_time, attempt, self.max_retries,
                )
                time.sleep(wait_time)

        raise RuntimeError("Unreachable transcript retry state")

    @staticmethod
    def _is_request_blocked(exc: Exception) -> bool:
        """Recognize library and HTTP variants of IP/request blocking errors."""
        error_name = type(exc).__name__.lower()
        error_text = str(exc).lower()
        return (
            error_name in {"ipblocked", "requestblocked"}
            or "ip blocked" in error_text
            or "request blocked" in error_text
        )
    @staticmethod
    def _failed_result(video_id: str, exc: Exception) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        return (
            {
                "video_id": video_id,
                "language": "",
                "language_code": "",
                "is_generated": False,
                "segment_count": 0,
                "full_text": "",
                "collected_at": utc_now_iso(),
                "transcript_status": "failed",
                "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            },
            [],
        )

    @staticmethod
    def _no_transcript_result(video_id: str, exc: Exception) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        return (
            {
                "video_id": video_id,
                "language": "",
                "language_code": "",
                "is_generated": False,
                "segment_count": 0,
                "full_text": "",
                "collected_at": utc_now_iso(),
                "transcript_status": "NO_TRANSCRIPT",
                "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            },
            [],
        )


class TranscriptCollectionBlocked(RuntimeError):
    """Stop the transcript phase after YouTube reports an IP/request block."""

    def __init__(self, video_id: str, cause: Exception):
        self.video_id = video_id
        self.cause = cause
        super().__init__(f"Transcript requests blocked for {video_id}: {cause}")


def ensure_transcript_table(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_transcripts (
                video_id TEXT PRIMARY KEY,
                transcript_status TEXT NOT NULL,
                language TEXT NOT NULL,
                language_code TEXT NOT NULL,
                is_generated INTEGER NOT NULL,
                segment_count INTEGER NOT NULL,
                full_text TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                error TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_youtube_transcripts_status "
            "ON youtube_transcripts(transcript_status)"
        )
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(youtube_transcripts)")
        }
        if "metadata_json" not in columns:
            connection.execute(
                "ALTER TABLE youtube_transcripts "
                "ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
            )


def upsert_transcript(db_path: Path, transcript: Dict[str, Any]) -> None:
    ensure_transcript_table(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO youtube_transcripts (
                video_id, transcript_status, language, language_code, is_generated,
                segment_count, full_text, collected_at, error, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                transcript_status=excluded.transcript_status,
                language=excluded.language,
                language_code=excluded.language_code,
                is_generated=excluded.is_generated,
                segment_count=excluded.segment_count,
                full_text=excluded.full_text,
                collected_at=excluded.collected_at,
                error=excluded.error,
                metadata_json=excluded.metadata_json
            """,
            (
                str(transcript.get("video_id", "")),
                str(transcript.get("transcript_status", "failed")),
                str(transcript.get("language", "")),
                str(transcript.get("language_code", "")),
                int(bool(transcript.get("is_generated", False))),
                safe_int(transcript.get("segment_count")),
                str(transcript.get("full_text", "")),
                str(transcript.get("collected_at", utc_now_iso())),
                str(transcript.get("error", "")),
                json.dumps(
                    {
                        "title": transcript.get("title", ""),
                        "channel_title": transcript.get("channel_title", ""),
                        "creator_names": transcript.get("creator_names", []),
                        "gender_contexts": transcript.get("gender_contexts", []),
                        "candidate_score": transcript.get("candidate_score", 0),
                    },
                    ensure_ascii=False,
                ),
            ),
        )


def load_transcripts_from_database(db_path: Path) -> List[Dict[str, Any]]:
    ensure_transcript_table(db_path)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT video_id, transcript_status, language, language_code, is_generated,
                   segment_count, full_text, collected_at, error, metadata_json
            FROM youtube_transcripts
            ORDER BY collected_at, video_id
            """
        ).fetchall()
    transcripts: List[Dict[str, Any]] = []
    for row in rows:
        try:
            metadata = json.loads(row[9]) if row[9] else {}
        except json.JSONDecodeError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        transcripts.append({
            "video_id": row[0], "transcript_status": row[1], "language": row[2],
            "language_code": row[3], "is_generated": bool(row[4]),
            "segment_count": row[5], "full_text": row[6], "collected_at": row[7], "error": row[8],
            **metadata,
        })
    return transcripts


def saved_transcript_statuses(db_path: Path) -> Dict[str, str]:
    return {
        str(row["video_id"]): str(row["transcript_status"])
        for row in load_transcripts_from_database(db_path)
    }


# ============================================================
# 6. 점수 / creator resolve
# ============================================================


def calculate_candidate_scores(videos: pd.DataFrame) -> pd.DataFrame:
    if videos.empty:
        return videos
    df = videos.copy()
    published = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    age_days = (pd.Timestamp.now(tz="UTC") - published).dt.total_seconds().div(86400).fillna(9999).clip(lower=0.25)
    df["age_days"] = age_days
    df["view_velocity_est"] = df["view_count"].div(age_days)
    df["like_rate"] = df["like_count"].div(df["view_count"].clip(lower=1))
    df["comment_rate"] = df["comment_count"].div(df["view_count"].clip(lower=1))
    freshness = (1 / age_days).rank(pct=True)
    velocity = df["view_velocity_est"].rank(pct=True)
    engagement = (df["like_rate"] + df["comment_rate"] * 2).rank(pct=True)
    df["candidate_score"] = (velocity * 0.55 + engagement * 0.25 + freshness * 0.20) * 100
    return df.sort_values("candidate_score", ascending=False)


def load_resolved_cache() -> Dict[str, Dict[str, Any]]:
    if not RESOLVED_CREATORS_JSON.exists():
        return {}
    try:
        rows = json.loads(RESOLVED_CREATORS_JSON.read_text(encoding="utf-8"))
        return {str(r.get("creator_name", "")): r for r in rows if r.get("creator_name") and r.get("channel_id")}
    except Exception:
        return {}


def resolve_creators(yt: YouTubeCollector, creators: List[Dict[str, Any]], force: bool = False) -> List[Dict[str, Any]]:
    cache = {} if force else load_resolved_cache()
    resolved: List[Dict[str, Any]] = []

    for idx, creator in enumerate(creators, start=1):
        name = str(creator.get("name", "")).strip()
        gender = str(creator.get("gender", "공통"))
        configured_channel_id = str(creator.get("channel_id", "")).strip()
        handle = str(creator.get("handle", "")).strip()
        fashion_filter = bool(creator.get("fashion_filter", True))

        channel: Optional[Dict[str, Any]] = None
        resolution_method = ""

        if configured_channel_id:
            rows = yt.get_current_channels([configured_channel_id])
            channel = rows[0] if rows else None
            resolution_method = "configured_channel_id"
        elif handle:
            channel = yt.channel_by_handle(handle)
            resolution_method = "configured_handle"
        elif name in cache:
            cached_id = str(cache[name].get("channel_id", ""))
            rows = yt.get_current_channels([cached_id]) if cached_id else []
            channel = rows[0] if rows else None
            resolution_method = "cache"
        else:
            print(f"[RESOLVE SEARCH {idx}/{len(creators)}] {name}")
            channel = yt.resolve_channel_name(name)
            resolution_method = "search"

        if not channel:
            print(f"[RESOLVE FAILED] {name}")
            resolved.append({
                "creator_name": name,
                "gender": gender,
                "fashion_filter": fashion_filter,
                "channel_id": "",
                "channel_title": "",
                "uploads_playlist_id": "",
                "resolution_method": "failed",
                "resolved_at": utc_now_iso(),
            })
            continue

        row = {
            "creator_name": name,
            "gender": gender,
            "fashion_filter": fashion_filter,
            "channel_id": channel.get("channel_id", ""),
            "channel_title": channel.get("channel_title", ""),
            "custom_url": channel.get("custom_url", ""),
            "subscriber_count": channel.get("subscriber_count", 0),
            "channel_video_count": channel.get("channel_video_count", 0),
            "uploads_playlist_id": channel.get("uploads_playlist_id", ""),
            "resolution_method": resolution_method,
            "resolved_at": utc_now_iso(),
        }
        print(f"[RESOLVED] {name} -> {row['channel_title']} ({row['channel_id']})")
        resolved.append(row)

    write_json_records(resolved, RESOLVED_CREATORS_JSON)
    return resolved


# ============================================================
# 7. 전체 파이프라인
# ============================================================


def collect_all(
    days_back: int,
    videos_per_creator: int,
    comment_pages: int,
    include_comment_authors: bool,
    include_nonfashion: bool,
    force_resolve: bool,
) -> None:
    quota = QuotaGuard()
    yt = YouTubeCollector(YOUTUBE_API_KEY, quota)
    creators = load_creator_config()

    print(f"[START] creators={len(creators)}, days={days_back}, per_creator={videos_per_creator}")

    # 1) 크리에이터 채널 확인/캐시
    resolved = resolve_creators(yt, creators, force=force_resolve)
    valid_resolved = [r for r in resolved if r.get("channel_id") and r.get("uploads_playlist_id")]
    write_json_records(valid_resolved, CREATORS_CURRENT_JSON)
    print(f"[INFO] resolved creators={len(valid_resolved)}/{len(creators)}")

    # 2) 각 채널 uploads playlist에서 최근 영상 ID 수집
    matches: List[Dict[str, Any]] = []
    for i, creator in enumerate(valid_resolved, start=1):
        print(f"[UPLOADS {i}/{len(valid_resolved)}] {creator['creator_name']}")
        rows = yt.uploads_playlist_items(
            playlist_id=str(creator.get("uploads_playlist_id", "")),
            creator_name=str(creator.get("creator_name", "")),
            gender=str(creator.get("gender", "공통")),
            days_back=days_back,
            max_videos=videos_per_creator,
        )
        for row in rows:
            row["creator_channel_title"] = creator.get("channel_title", "")
            row["fashion_filter"] = creator.get("fashion_filter", True)
        matches.extend(rows)
        time.sleep(0.02)

    matches_df = pd.DataFrame(matches)
    write_json_df(matches_df, CREATOR_VIDEO_MATCHES_JSON)
    candidate_video_ids = list(dict.fromkeys(matches_df.get("video_id", pd.Series(dtype=str)).dropna().astype(str).tolist()))
    known_video_ids = load_known_video_ids()
    video_ids = [video_id for video_id in candidate_video_ids if video_id not in known_video_ids]
    print(
        f"[INFO] creator-video matches={len(matches_df)}, "
        f"new videos={len(video_ids)}, already stored={len(candidate_video_ids) - len(video_ids)}"
    )

    # 3) 영상 상세/반응
    videos_df = pd.DataFrame(yt.video_details(video_ids))
    if not videos_df.empty and not matches_df.empty:
        creator_context = matches_df.groupby("video_id").agg(
            creator_names=("creator_name", lambda s: sorted(set(s))),
            gender_contexts=("gender_context", lambda s: sorted(set(s))),
            creator_channel_titles=("creator_channel_title", lambda s: sorted(set(s))),
            fashion_filter_required=("fashion_filter", "max"),
        ).reset_index()
        videos_df = videos_df.merge(creator_context, on="video_id", how="left")

        # 전용 채널이라도 설정상 fashion_filter=True인 경우 메타데이터 기반 1차 필터
        videos_df["fashion_relevant"] = videos_df.apply(
            lambda r: is_fashion_relevant(r.to_dict()) if bool(r.get("fashion_filter_required", True)) else True,
            axis=1,
        )
        if not include_nonfashion:
            before = len(videos_df)
            videos_df = videos_df[videos_df["fashion_relevant"]].copy()
            print(f"[FILTER] fashion relevant {len(videos_df)}/{before}")

        videos_df = calculate_candidate_scores(videos_df)

    merge_json_records(dataframe_records(videos_df), VIDEOS_JSON, ("video_id",))
    if not videos_df.empty:
        snapshot_cols = ["video_id", "collected_at", "view_count", "like_count", "comment_count", "candidate_score"]
        append_jsonl_df(videos_df[snapshot_cols], VIDEO_SNAPSHOTS_JSONL)

    # 4) 현재 채널 통계
    channel_ids = [r.get("channel_id", "") for r in valid_resolved]
    channels_df = pd.DataFrame(yt.get_current_channels(channel_ids))
    if not channels_df.empty:
        creator_by_id = {str(r.get("channel_id")): r for r in valid_resolved}
        channels_df["creator_name"] = channels_df["channel_id"].map(lambda x: creator_by_id.get(str(x), {}).get("creator_name", ""))
        channels_df["gender"] = channels_df["channel_id"].map(lambda x: creator_by_id.get(str(x), {}).get("gender", ""))
    write_json_df(channels_df, CHANNELS_JSON)
    if not channels_df.empty:
        append_jsonl_df(
            channels_df[["channel_id", "creator_name", "gender", "collected_at", "channel_view_count", "subscriber_count", "channel_video_count"]],
            CHANNEL_SNAPSHOTS_JSONL,
        )

    # 5) 선택된 모든 영상 댓글 1페이지(기본 최대 100 top-level thread) 수집
    comment_rows: List[Dict[str, Any]] = []
    for i, row in enumerate(videos_df.itertuples(index=False), start=1):
        if not quota.can_general(1):
            print("[STOP] general quota hard limit before comments")
            break
        print(f"[COMMENTS] {i}/{len(videos_df)} {row.video_id}")
        comment_rows.extend(yt.comment_threads(row.video_id, pages=comment_pages, include_authors=include_comment_authors))
        time.sleep(0.02)
    comments_df = pd.DataFrame(comment_rows)
    merge_json_records(
        dataframe_records(comments_df), COMMENTS_JSON, ("video_id", "comment_id")
    )
    if not comments_df.empty:
        cols = ["video_id", "comment_id", "parent_id", "is_reply", "like_count", "total_reply_count", "collected_at"]
        append_jsonl_df(comments_df[cols], COMMENT_SNAPSHOTS_JSONL)

    # Whisper transcription is run by whisper_transcriber.py after collection.
    # The deprecated youtube-transcript-api / SQLite transcript flow is not used.
    quota.save()
    print("\n[COLLECTION DONE]")
    print(f"creators: {len(valid_resolved)}")
    print(f"videos kept: {len(videos_df)}")
    print(f"comments rows: {len(comments_df)}")
    print(f"output: {OUTPUT_DIR.resolve()}")
    return

    # 6) 선택된 모든 영상 자막 시도
    transcript_status_by_video = saved_transcript_statuses(DATABASE_PATH)
    transcript_targets = read_json_records(VIDEOS_JSON)
    tc = TranscriptCollector(languages=["ko", "en"])
    stopped_by_block = False
    for i, video in enumerate(transcript_targets, start=1):
        video_id = str(video.get("video_id", ""))
        if not video_id:
            continue
        previous_status = transcript_status_by_video.get(video_id)
        if previous_status in {"success", "NO_TRANSCRIPT"}:
            print(f"[TRANSCRIPT SKIP] {video_id}: {previous_status}")
            continue

        print(f"[TRANSCRIPT] {i}/{len(transcript_targets)} {video_id}")
        try:
            doc, _segments = tc.fetch(video_id)
        except TranscriptCollectionBlocked as exc:
            logging.error("[TRANSCRIPT STOP] %s", exc)
            stopped_by_block = True
            break

        doc["title"] = video.get("title", "")
        doc["channel_title"] = video.get("channel_title", "")
        doc["creator_names"] = video.get("creator_names", [])
        doc["gender_contexts"] = video.get("gender_contexts", [])
        doc["candidate_score"] = video.get("candidate_score", 0)
        upsert_transcript(DATABASE_PATH, doc)
        transcript_status_by_video[video_id] = str(doc["transcript_status"])
        write_json_records(load_transcripts_from_database(DATABASE_PATH), TRANSCRIPTS_JSON)

        if i == len(transcript_targets):
            continue
        if i % DEFAULT_TRANSCRIPT_BATCH_SIZE == 0:
            cooldown_sec = random.uniform(*DEFAULT_TRANSCRIPT_COOLDOWN_RANGE)
            logging.info(
                "자막 %s개 수집 완료. IP 보호를 위해 %.1f초 쿨다운합니다.",
                i,
                cooldown_sec,
            )
            time.sleep(cooldown_sec)
        elif transcript_sleep_sec:
            delay_sec = random.uniform(transcript_sleep_sec, transcript_sleep_sec + 2.0)
            time.sleep(delay_sec)

    transcript_records = load_transcripts_from_database(DATABASE_PATH)
    write_json_records(transcript_records, TRANSCRIPTS_JSON)
    if stopped_by_block:
        print("[TRANSCRIPT STOP] Request blocking detected; saved results will resume next run.")

    # 7) 영상 단위 통합 문서
    video_records = read_json_records(VIDEOS_JSON)
    channel_records = read_json_records(CHANNELS_JSON)
    comment_records = read_json_records(COMMENTS_JSON)
    match_records = read_json_records(CREATOR_VIDEO_MATCHES_JSON)

    channels_by_id = {str(x.get("channel_id", "")): x for x in channel_records}
    comments_by_video: Dict[str, List[Dict[str, Any]]] = {}
    for x in comment_records:
        comments_by_video.setdefault(str(x.get("video_id", "")), []).append(x)
    transcripts_by_video = {str(x.get("video_id", "")): x for x in transcript_records}
    matches_by_video: Dict[str, List[Dict[str, Any]]] = {}
    for x in match_records:
        matches_by_video.setdefault(str(x.get("video_id", "")), []).append(x)

    documents: List[Dict[str, Any]] = []
    for video in video_records:
        vid = str(video.get("video_id", ""))
        cid = str(video.get("channel_id", ""))
        tmeta = transcripts_by_video.get(vid)
        documents.append(
            {
                "_id": vid,
                "schema_version": "feedit.youtube.creator_video.v2",
                "collected_at": video.get("collected_at"),
                "source": "youtube_creator_channels",
                "creator_matches": matches_by_video.get(vid, []),
                "video": video,
                "channel": channels_by_id.get(cid),
                "comments": comments_by_video.get(vid, []),
                "transcript": {"metadata": tmeta} if tmeta else None,
                # NLP 단계에서 추후 채우기 위한 자리
                "fashion_analysis": None,
            }
        )

    existing_documents: Dict[str, Dict[str, Any]] = {}
    if VIDEO_DOCUMENTS_JSONL.exists():
        with VIDEO_DOCUMENTS_JSONL.open(encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                document = json.loads(line)
                if document.get("_id"):
                    existing_documents[str(document["_id"])] = document
    existing_documents.update({str(doc["_id"]): doc for doc in documents})
    VIDEO_DOCUMENTS_JSONL.write_text(
        "".join(
            jsonl_dumps(doc) + "\n"
            for doc in existing_documents.values()
        ),
        encoding="utf-8",
    )
    DAILY_BUNDLE_JSON.write_text(
        json.dumps(
            {
                "schema_version": "feedit.youtube.daily_bundle.v2",
                "collected_at": utc_now_iso(),
                "creators": valid_resolved,
                "videos": video_records,
                "channels": channel_records,
                "comments": comment_records,
                "transcripts": transcript_records,
                "creator_video_matches": match_records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    quota.save()
    database_path = sync_database_if_available(OUTPUT_DIR, DATABASE_PATH)
    print("\n[DONE]")
    print(f"creators: {len(valid_resolved)}")
    print(f"videos kept: {len(videos_df)}")
    print(f"comments rows: {len(comments_df)}")
    print(f"transcripts: {len(transcripts_df)}")
    print(f"search calls used: {quota.search_calls}/{quota.search_limit}")
    print(f"general units used: {quota.general_units}/{quota.general_limit}")
    print(f"output: {OUTPUT_DIR.resolve()}")
    if database_path is not None:
        print(f"database: {database_path.resolve()}")


def sync_database_if_available(data_dir: Path, db_path: Path) -> Optional[Path]:
    """Synchronize SQLite output when the optional database module is present."""
    if str(PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR))

    try:
        from youtube_db import sync_database
    except ModuleNotFoundError as exc:
        if exc.name != "youtube_db":
            raise
        print("[WARN] Skipping SQLite synchronization: optional youtube_db module was not found.")
        return None

    return sync_database(data_dir=data_dir, db_path=db_path)


# ============================================================
# 8. CLI
# ============================================================


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="FEEDIT YouTube creator collector v5")
    p.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK, help="최근 N일 이내 업로드 영상")
    p.add_argument("--videos-per-creator", type=int, default=DEFAULT_VIDEOS_PER_CREATOR, help="크리에이터당 최대 영상 수")
    p.add_argument("--comment-pages", type=int, default=DEFAULT_COMMENT_PAGES_PER_VIDEO, help="영상당 댓글 페이지 수(페이지당 최대 100 thread)")
    p.add_argument("--include-comment-authors", action="store_true", help="댓글 작성자 표시명/채널 ID도 저장")
    p.add_argument("--include-nonfashion", action="store_true", help="패션 키워드가 없는 채널 영상도 포함")
    p.add_argument("--force-resolve", action="store_true", help="저장된 channel_id 캐시를 무시하고 채널명을 다시 검색")
    p.add_argument("--dry-run", action="store_true", help="API 호출 없이 .env/크리에이터 설정만 확인")
    return p


def main() -> None:
    args = build_parser().parse_args()
    creators = load_creator_config()

    if args.dry_run:
        print(f"creator config: {CREATOR_CONFIG_PATH.resolve()}")
        print(f"creators: {len(creators)}")
        print(f"YOUTUBE_API_KEY in .env: {'OK' if YOUTUBE_API_KEY else 'MISSING'}")
        for c in creators:
            print(f"- {c.get('gender','')} | {c.get('name','')} | channel_id={c.get('channel_id','') or '-'} | handle={c.get('handle','') or '-'}")
        return

    collect_all(
        days_back=max(1, args.days),
        videos_per_creator=max(1, min(50, args.videos_per_creator)),
        comment_pages=max(1, args.comment_pages),
        include_comment_authors=args.include_comment_authors,
        include_nonfashion=args.include_nonfashion,
        force_resolve=args.force_resolve,
    )


if __name__ == "__main__":
    main()
