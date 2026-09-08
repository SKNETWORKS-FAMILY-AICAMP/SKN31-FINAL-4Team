from __future__ import annotations

from .client import (
    YoutubeClient,
)
from .constants import (
    API_PAGE_SIZE,
    CHANNELS_API_URL,
    COMMENT_ORDER,
    COMMENT_PAGE_SIZE,
    COMMENT_PARTS,
    COMMENT_THREADS_API_URL,
    DEFAULT_COMMENT_LIMIT,
    DEFAULT_VIDEO_LIMIT,
    PLAYLIST_ITEMS_API_URL,
    VIDEOS_API_URL,
    VIDEO_PARTS,
)
from .exceptions import (
    YoutubeCollectError,
)
from .parser import (
    YoutubeParser,
)


class YoutubeCollector:

    def __init__(
        self,
        *,
        api_key: str,
    ):
        self.client = YoutubeClient(
            api_key=api_key,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        self.close()

    # ============================================================
    # PROFILE
    # ============================================================

    def collect_profile(
        self,
        channel_id: str,
        *,
        seed: dict | None = None,
    ) -> dict:

        body = self.client.get_json(
            CHANNELS_API_URL,

            params={
                "part": (
                    "snippet,"
                    "statistics,"
                    "contentDetails,"
                    "brandingSettings"
                ),

                "id": (
                    channel_id
                ),
            },
        )

        items = (
            body.get("items")
            or []
        )

        if not items:
            raise YoutubeCollectError(
                "YouTube 채널을 찾을 수 없습니다: "
                f"{channel_id}"
            )

        return YoutubeParser.parse_channel(
            items[0],
            seed=seed,
        )

    # ============================================================
    # UPLOADS PLAYLIST
    # ============================================================

    @staticmethod
    def uploads_playlist_id(
        channel_id: str,
    ) -> str:
        """
        채널의 업로드 재생목록 ID.

        YouTube 규칙상 채널 ID의 'UC' 접두사를
        'UU'로 바꾼 값과 동일하다.
        ContentProfile에 저장된 값이 없을 때의 폴백.
        """

        channel_id = str(channel_id or "").strip()

        if not channel_id:
            raise YoutubeCollectError(
                "channel_id가 비어 있습니다."
            )

        if channel_id.startswith("UC"):
            return "UU" + channel_id[2:]

        return channel_id

    # ============================================================
    # VIDEO ID DISCOVERY
    # ============================================================

    def discover_video_ids(
        self,
        playlist_id: str,
        *,
        limit: int = DEFAULT_VIDEO_LIMIT,
    ) -> list[dict]:
        """
        업로드 재생목록에서 최근 영상 ID를 최신순으로 수집.

        비용: 요청 1건당 1 unit.
        limit이 50 이하이면 1회 호출로 끝난다.
        """

        limit = max(
            1,
            int(limit or DEFAULT_VIDEO_LIMIT),
        )

        collected: list[dict] = []
        page_token = None

        while len(collected) < limit:

            params = {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(
                    API_PAGE_SIZE,
                    limit - len(collected),
                ),
            }

            if page_token:
                params["pageToken"] = page_token

            body = self.client.get_json(
                PLAYLIST_ITEMS_API_URL,
                params=params,
            )

            items = (
                YoutubeParser
                .parse_playlist_items(body)
            )

            if not items:
                break

            collected.extend(items)

            page_token = body.get("nextPageToken")

            if not page_token:
                break

        return collected[:limit]

    # ============================================================
    # VIDEO DETAIL
    # ============================================================

    def collect_video_details(
        self,
        video_ids: list[str],
        *,
        channel_id: str | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """
        영상 상세를 50건씩 묶어 조회한다.

        비용: 50건당 1 unit.
        """

        videos: list[dict] = []
        errors: list[dict] = []

        ids = [
            str(v).strip()
            for v in (video_ids or [])
            if str(v or "").strip()
        ]

        for start in range(
            0,
            len(ids),
            API_PAGE_SIZE,
        ):
            chunk = ids[start: start + API_PAGE_SIZE]

            try:
                body = self.client.get_json(
                    VIDEOS_API_URL,
                    params={
                        "part": VIDEO_PARTS,
                        "id": ",".join(chunk),
                        "maxResults": API_PAGE_SIZE,
                    },
                )

            except Exception as exc:
                errors.append(
                    {
                        "video_ids": chunk,
                        "error_type": (
                            exc.__class__.__name__
                        ),
                        "error_message": str(exc),
                    }
                )
                continue

            for item in (body.get("items") or []):
                try:
                    videos.append(
                        YoutubeParser.parse_video(
                            item,
                            channel_id=channel_id,
                        )
                    )

                except Exception as exc:
                    errors.append(
                        {
                            "video_id": (
                                item.get("id")
                                if isinstance(item, dict)
                                else None
                            ),
                            "error_type": (
                                exc.__class__.__name__
                            ),
                            "error_message": str(exc),
                        }
                    )

        return videos, errors

    # ============================================================
    # VIDEOS (MAIN)
    # ============================================================

    def collect_videos(
        self,
        channel_id: str,
        *,
        playlist_id: str | None = None,
        limit: int = DEFAULT_VIDEO_LIMIT,
    ) -> dict:
        """
        채널의 최근 영상 메타와 지표를 수집한다.

            playlistItems (영상 ID 목록)
            -> videos      (상세 + 통계)
        """

        playlist_id = (
            playlist_id
            or self.uploads_playlist_id(channel_id)
        )

        discovered = self.discover_video_ids(
            playlist_id,
            limit=limit,
        )

        video_ids = [
            item["video_id"]
            for item in discovered
        ]

        videos, errors = (
            self.collect_video_details(
                video_ids,
                channel_id=channel_id,
            )
        )

        return {
            "playlist_id": playlist_id,
            "videos": videos,
            "errors": errors,
            "summary": {
                "discovered_count": len(video_ids),
                "success_count": len(videos),
                "failure_count": (
                    len(video_ids) - len(videos)
                ),
            },
        }

    # ============================================================
    # COMMENT
    # ============================================================

    def collect_comments(
        self,
        video_id: str,
        *,
        limit: int = DEFAULT_COMMENT_LIMIT,
    ) -> dict:
        """
        영상 1건의 댓글을 수집한다.

        비용: 요청 1건당 1 unit (최대 100건).
        대댓글은 같은 응답에 최대 5건까지 무료로 포함된다.

        댓글이 꺼진 영상은 403을 준다.
        실패가 아니라 정상 상태로 취급하고 skipped로 표시한다.
        """

        limit = max(
            1,
            int(limit or DEFAULT_COMMENT_LIMIT),
        )

        comments: list[dict] = []
        page_token = None
        disabled = False
        error = None

        while len(comments) < limit:

            params = {
                "part": COMMENT_PARTS,
                "videoId": video_id,
                "order": COMMENT_ORDER,
                "maxResults": min(
                    COMMENT_PAGE_SIZE,
                    limit - len(comments),
                ),
                "textFormat": "plainText",
            }

            if page_token:
                params["pageToken"] = page_token

            try:
                body = self.client.get_json(
                    COMMENT_THREADS_API_URL,
                    params=params,
                )

            except Exception as exc:
                message = str(exc)

                # 댓글 비활성 / 비공개 / 삭제된 영상
                if (
                    "403" in message
                    or "404" in message
                    or "commentsDisabled" in message
                ):
                    disabled = True

                else:
                    error = {
                        "error_type": (
                            exc.__class__.__name__
                        ),
                        "error_message": message,
                    }

                break

            parsed = (
                YoutubeParser
                .parse_comment_threads(
                    body,
                    video_id=video_id,
                )
            )

            if not parsed:
                break

            comments.extend(parsed)

            page_token = body.get("nextPageToken")

            if not page_token:
                break

        top_level = [
            c
            for c in comments
            if not c.get("is_reply")
        ]

        return {
            "video_id": video_id,
            "comments": comments,
            "disabled": disabled,
            "error": error,
            "summary": {
                "total_count": len(comments),
                "top_level_count": len(top_level),
                "reply_count": (
                    len(comments) - len(top_level)
                ),
            },
        }

    # ============================================================
    # MULTIPLE PROFILES
    # ============================================================

    def collect_profiles(
        self,
        seeds: list[dict],
    ) -> dict:

        profiles = []
        errors = []

        for seed in seeds:

            channel_id = (
                seed.get(
                    "channel_id"
                )
            )

            if not channel_id:
                errors.append(
                    {
                        "seed": seed,
                        "error": (
                            "channel_id 없음"
                        ),
                    }
                )
                continue

            try:
                profile = (
                    self.collect_profile(
                        channel_id,
                        seed=seed,
                    )
                )

                profiles.append(
                    profile
                )

            except Exception as exc:
                errors.append(
                    {
                        "channel_id": (
                            channel_id
                        ),

                        "seed_name": (
                            seed.get(
                                "name"
                            )
                        ),

                        "error_type": (
                            exc
                            .__class__
                            .__name__
                        ),

                        "error_message": (
                            str(exc)
                        ),
                    }
                )

        return {
            "profiles": profiles,

            "summary": {
                "requested_count": (
                    len(seeds)
                ),

                "success_count": (
                    len(profiles)
                ),

                "failure_count": (
                    len(errors)
                ),
            },

            "errors": errors,
        }