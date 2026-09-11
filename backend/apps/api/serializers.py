from rest_framework import serializers

from apps.core.models.collection import CrawlRun, CrawlTarget, Source


class CrawlTargetSerializer(serializers.ModelSerializer):
    source = serializers.SlugRelatedField(
        slug_field="code",
        queryset=Source.objects.all(),
    )

    class Meta:
        model = CrawlTarget
        fields = [
            "id",
            "source",
            "name",
            "target_type",
            "target_url",
            "collection_mode",
            "params",
            "interval_minutes",
            "priority",
            "is_active",
            "last_crawled_at",
            "next_crawl_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "last_crawled_at",
            "next_crawl_at",
            "created_at",
            "updated_at",
        ]


class CrawlRunSerializer(serializers.ModelSerializer):
    source = serializers.SlugRelatedField(
        read_only=True,
        slug_field="code",
    )

    class Meta:
        model = CrawlRun
        fields = [
            "id",
            "source",
            "crawl_target",
            "run_type",
            "target",
            "params",
            "status",
            "celery_task_id",
            "started_at",
            "finished_at",
            "discovered_count",
            "success_count",
            "failure_count",
            "error_code",
            "error_message",
            "created_at",
        ]
        read_only_fields = fields