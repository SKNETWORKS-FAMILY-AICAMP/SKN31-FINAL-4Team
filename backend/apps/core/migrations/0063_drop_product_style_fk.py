"""스타일 단일 FK(``commerce.product.style_id``) 를 걷어낸다. (2026-09-21)

── 왜 ────────────────────────────────────────────────────────
0039 이 ``Product.style`` 을 더했을 때는 상품 하나에 스타일이 **하나만** 박혔다.
DB 팀이 스타일을 **여러 개** 달 수 있게 연결 표로 옮기면서 운영 스키마에서
이 칸을 떼어냈고, 모델만 옛 칸을 계속 바라봐서 ``product`` 를 통째로 읽는
모든 조회가 터졌다 — ``column commerce.product.style_id does not exist``:
  · ``/api/salmal/cards``   → 살!말? 카드가 하나도 안 나온다
  · ``/api/facets?style=…`` → 스타일을 고르면 패싯이 안 나온다
  · ``/api/auth/…`` 취향    → 찜한 상품 조회 (select_related("product__…"))

이제 상품의 스타일은 ``commerce.product_term`` (term_type='STYLE') 에서 읽는다.
이미 그 표로 세던 패싯·추천은 그대로 동작하므로 바꿀 게 없다.

── 하는 일 ───────────────────────────────────────────────────
Django 상태에서는 인덱스와 칸을 지우고, 실제 DB 에는 **있을 때만** DROP 을 건다.
운영(이미 떼어낸 DB)에서는 아무 일도 하지 않고, 아직 칸이 남아 있는 개발 DB 에서는
그때 정리된다. 어느 쪽이든 두 번 돌려도 안전하다.
"""

from django.db import migrations

DROP = """
DROP INDEX IF EXISTS "commerce"."idx_product_style";
ALTER TABLE "commerce"."product" DROP COLUMN IF EXISTS "style_id";
"""

# 되돌리기 — 칸과 인덱스를 되살린다 (데이터는 돌아오지 않는다).
RESTORE = """
ALTER TABLE "commerce"."product" ADD COLUMN IF NOT EXISTS "style_id" bigint NULL;
CREATE INDEX IF NOT EXISTS "idx_product_style" ON "commerce"."product" ("style_id");
"""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0062_productreview_platformmetricdaily_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(DROP, RESTORE)],
            state_operations=[
                migrations.RemoveIndex(model_name="product", name="idx_product_style"),
                migrations.RemoveField(model_name="product", name="style"),
            ],
        ),
    ]
