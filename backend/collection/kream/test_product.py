from __future__ import annotations

import os
from pprint import pprint

from collection.kream.collector import KreamCollector
from collection.kream.s3_sink import KreamS3Sink


PRODUCT_URL = "https://kream.co.kr/products/842180"


def main():
    bucket = os.getenv("AWS_S3_BUCKET", "feedit-data-team4")
    region = os.getenv("AWS_REGION", "ap-northeast-2")

    print("[1/2] KREAM PRODUCT COLLECT")

    with KreamCollector() as collector:
        data = collector.collect_product(PRODUCT_URL)

    pprint(data["product"])
    pprint(data["snapshot"])
    print("ranking_signals:", data["ranking_signals"])
    print("options:", len(data["options"]))
    print("sales:", len(data["market"]["sales"]))
    print("asks:", len(data["market"]["asks"]))
    print("bids:", len(data["market"]["bids"]))
    print("listings:", len(data["market"]["listings"]))

    print("[2/2] S3 UPLOAD")

    sink = KreamS3Sink(
        bucket=bucket,
        region_name=region,
    )

    pprint(sink.save_product(data))


if __name__ == "__main__":
    main()
