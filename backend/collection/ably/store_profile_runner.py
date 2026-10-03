"""Run a registered STORE_PROFILE target through the shared Django runner."""
from __future__ import annotations
import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run an ABLY STORE_PROFILE CrawlTarget")
    parser.add_argument("--target-id", type=int, required=True)
    args = parser.parse_args(argv)
    import django
    django.setup()
    from apps.core.models import CrawlTarget
    from collection.common.runner import run_target
    target = CrawlTarget.objects.select_related("source").get(pk=args.target_id)
    if target.source.code.upper() != "ABLY" or target.target_type.upper() not in {"STORE", "STORE_PROFILE"}:
        raise ValueError("An ABLY STORE_PROFILE CrawlTarget is required")
    result = run_target(target.id)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return result


if __name__ == "__main__":
    main()
