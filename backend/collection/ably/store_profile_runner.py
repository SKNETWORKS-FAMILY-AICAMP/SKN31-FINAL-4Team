from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .constants import BRAND_DEPARTMENT_CATEGORIES, COMPONENT_LIST_API_URL
from .store_profile_collector import AblyStoreProfileCollector
from .store_profile_pipeline import AblyStoreProfilePipeline


load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="ABLY 브랜드관 랭킹을 S3 RAW로 수집")
    parser.add_argument(
        "--category-snos",
        nargs="+",
        type=int,
        choices=list(BRAND_DEPARTMENT_CATEGORIES),
        default=None,
    )
    parser.add_argument("--max-requests", type=int, default=None)
    parser.add_argument("--bucket", default=os.getenv("AWS_STORAGE_BUCKET_NAME"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "ap-northeast-2"))
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.bucket:
        raise SystemExit("AWS_STORAGE_BUCKET_NAME 또는 --bucket이 필요합니다.")

    def collector_factory():
        kwargs = {}
        if args.max_requests is not None:
            kwargs["max_requests"] = args.max_requests
        return AblyStoreProfileCollector(**kwargs)

    pipeline = AblyStoreProfilePipeline(
        bucket=args.bucket,
        region_name=args.region,
        collector_factory=collector_factory,
    )
    result = pipeline.run_target(
        target_type="STORE_PROFILE",
        target_url=COMPONENT_LIST_API_URL,
        params={"category_snos": args.category_snos},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("failure_count") and args.max_requests is None:
        raise SystemExit(2)
    return result


if __name__ == "__main__":
    main()
