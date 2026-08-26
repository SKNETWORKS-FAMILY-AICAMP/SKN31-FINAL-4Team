from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.crawler.models import YoutubeContent, YoutubeCreator
from apps.crawler.services.youtube_collection import (
    YouTubeCollectionError,
    YoutubeCollectionService,
)


def youtube(request):
    creators = YoutubeCreator.objects.prefetch_related("contents").order_by(
        "channel_name"
    )
    recent_contents = YoutubeContent.objects.select_related("creator").order_by(
        "-published_at", "-created_at"
    )[:30]
    return render(
        request,
        "crawler/youtube.html",
        {
            "creators": creators,
            "creator_count": creators.count(),
            "recent_contents": recent_contents,
            "selected_creator": None,
            "detector_result": None,
            "latest_video": None,
            "error": None,
        },
    )


def run_youtube_pipeline(request, creator_id):
    """Collect one creator's history or newly uploaded videos."""
    creator = get_object_or_404(YoutubeCreator, pk=creator_id)

    if request.method != "POST":
        return redirect("crawler:youtube")

    action = request.POST.get("action", "update")

    try:
        collector = YoutubeCollectionService()

        if action == "backfill":
            result = collector.collect_history(creator)
            action_label = "최근 1년 영상 수집"

        elif action == "update":
            result = collector.collect_updates(creator)
            action_label = "최근 영상 확인"

        else:
            messages.error(request, "알 수 없는 YouTube 수집 요청입니다.")
            return redirect("crawler:youtube")

    except YouTubeCollectionError as exc:
        messages.error(request, f"{creator.channel_name}: {exc}")
        return redirect("crawler:youtube")

    messages.success(
        request,
        f"{creator.channel_name} {action_label} 완료: "
        f"신규 {result.added}개, "
        f"중복 건너뜀 {result.skipped}개, "
        f"패션 필터 제외 {result.filtered_out}개.",
    )

    return redirect("crawler:youtube")


def overview(request):
    context = {
        "active_menu": "youtube",
        "active_tab": "overview",
    }

    return render(
        request,
        "crawler/youtube/overview.html",
        context,
    )


def channels(request):
    context = {
        "active_menu": "youtube",
        "active_tab": "channels",
    }

    return render(
        request,
        "crawler/youtube/channels.html",
        context,
    )
