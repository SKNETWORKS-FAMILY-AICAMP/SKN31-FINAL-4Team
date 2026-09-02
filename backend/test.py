import json

from analysis.commerce.musinsa.normalizer import (
    MusinsaNormalizer,
)

with open(
    r"C:\SKN31-FINAL-4Team\backend\20260902T061616.json",
    "r",
    encoding="utf-8",
) as f:
    raw = json.load(f)

normalizer = MusinsaNormalizer()

result = normalizer.normalize_ranking(
    raw
)

print(
    "PRODUCT COUNT =",
    result["summary"]["product_count"],
)

first = result["products"][0]

print("\nBRAND")
print(first["brand"])

print("\nPRODUCT")
print(first["product"])

print("\nPRODUCT SOURCE")
print(first["product_source"])

print("\nSNAPSHOT")
print(first["snapshot"])

print("\nATTRIBUTES")
print(first["source_attributes"])

print("\nIMAGE COUNT")
print(len(first["images"]))