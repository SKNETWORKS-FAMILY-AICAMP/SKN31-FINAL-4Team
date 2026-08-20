from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.crawler.models import YoutubeContent, YoutubeCreator


def youtube(request):
    creators = YoutubeCreator.objects.prefetch_related("contents").order_by("channel_name")
    recent_contents = (
        YoutubeContent.objects.select_related("creator")
        .order_by("-published_at", "-created_at")[:30]
    )
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
    creator = get_object_or_404(YoutubeCreator, pk=creator_id)
    if request.method == "POST":
        action = request.POST.get("action", "update")
        # 실제 서비스/태스크 함수가 준비되면 여기서 호출하세요.
        # 예: run_youtube_creator.delay(creator.id, action=action)
        messages.info(request, f"{creator.channel_name}: {action} 요청을 받았습니다. Celery task를 이 위치에 연결하세요.")
    return redirect("crawler:youtube")
