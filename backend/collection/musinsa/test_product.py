from datetime import datetime

from collection.musinsa.collector import MusinsaCollector
from collection.common.s3 import S3Storage


url = "https://www.musinsa.com/products/7011611"

with MusinsaCollector() as collector:
    data = collector.collect_product(
        url,
        collect_options=True,
        collect_reviews=True,
        review_limit=10,
    )


goods_no = data["product"]["goods_no"]

now = datetime.now()

key = (
    f"raw/musinsa/product/"
    f"{now:%Y/%m/%d}/"
    f"{goods_no}/product.json"
)


storage = S3Storage(
    bucket="feedit-data-team4",
)

s3_uri = storage.upload_json(
    key=key,
    data=data,
)

print("S3 UPLOAD SUCCESS")
print(s3_uri)