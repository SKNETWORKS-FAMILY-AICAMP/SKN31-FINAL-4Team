from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


CARDS = [
    ("스웨이드 블루종 (버건디)", "ANDERSSON BELL", "assets/hi/f20.jpg", "ACTIVE"),
    ("셀비지 와이드 데님", "MUSINSA STANDARD", "assets/hi/f21.jpg", "ACTIVE"),
    ("퀼팅 다운 베스트", "NAUTICA", "assets/hi/f22.jpg", "ACTIVE"),
    ("스퀘어 토 로퍼", "RANDOM IDENTITIES", "assets/hi/f23.jpg", "ACTIVE"),
    ("울 발마칸 코트", "SOLEW", "assets/hi/f24.jpg", "ACTIVE"),
    ("니트 집업 카디건", "INSILENCE", "assets/hi/f25.jpg", "ACTIVE"),
    ("와이드 코듀로이 팬츠", "SOLEW", "assets/hi/f26.jpg", "ACTIVE"),
    ("레더 크로스 백", "MATIN KIM", "assets/hi/f27.jpg", "ACTIVE"),
    ("오버핏 울 블레이저", "AMOMENTO", "assets/hi/f28.jpg", "ACTIVE"),
    ("캐시미어 머플러", "LE 17 SEPTEMBRE", "assets/hi/f29.jpg", "ACTIVE"),
    ("워시드 후드 집업", "THISISNEVERTHAT", "assets/hi/f30.jpg", "ACTIVE"),
    ("베이직 옥스포드 셔츠", "MUSINSA STANDARD", "assets/hi/f31.jpg", "ACTIVE"),
    ("헤비 코튼 크루넥", "COS", "assets/hi/f32.jpg", "ACTIVE"),
    ("원턱 와이드 슬랙스", "UNIFORM BRIDGE", "assets/hi/f33.jpg", "ACTIVE"),
    ("삼바 OG", "ADIDAS", "assets/hi/f34.jpg", "ACTIVE"),
    ("레이어드 체인 목걸이", "CENTIME", "assets/hi/f35.jpg", "ACTIVE"),
    ("와이드 리넨 셔츠", "COS", "assets/hi/f02.jpg", "CLOSED"),
    ("스트랩 샌들", "RANDOM IDENTITIES", "assets/hi/f05.jpg", "CLOSED"),
    ("헤링본 트위드 재킷", "SOLEW", "assets/hi/f11.jpg", "CLOSED"),
    ("미니멀 크로스백", "MSTA", "assets/hi/f13.jpg", "CLOSED"),
    ("스트라이프 니트", "COS", "assets/hi/f04.jpg", "CLOSED"),
    ("카고 워크 팬츠", "CARHARTT WIP", "assets/hi/f06.jpg", "CLOSED"),
    ("레트로 러너 스니커즈", "NEW BALANCE", "assets/hi/f08.jpg", "CLOSED"),
    ("오버사이즈 후드티", "THISISNEVERTHAT", "assets/hi/f09.jpg", "CLOSED"),
    ("데님 셔츠 자켓", "LEVI'S", "assets/hi/f12.jpg", "CLOSED"),
    ("버킷햇", "KIJUN", "assets/hi/f15.jpg", "CLOSED"),
    ("스퀘어 선글라스", "GENTLE MONSTER", "assets/hi/f17.jpg", "CLOSED"),
    ("램스울 가디건", "LEMAIRE", "assets/hi/f03.jpg", "CLOSED"),
]


def seed_cards(apps, schema_editor):
    User = apps.get_model("auth", "User")
    AppUser = apps.get_model("core", "AppUser")
    VoteCard = apps.get_model("core", "VoteCard")
    user, _ = User.objects.get_or_create(
        username="feedit_system",
        defaults={"password": "!", "is_active": False, "first_name": "FEEDiT"},
    )
    profile, _ = AppUser.objects.get_or_create(user=user, defaults={"nickname": "FEEDiT"})
    for title, brand, image, status in CARDS:
        VoteCard.objects.get_or_create(
            title=title,
            defaults={
                "user": profile,
                "description": "FEEDiT 살말 초기 카드",
                "image_url": image,
                "tags": [brand],
                "status": status,
            },
        )


def unseed_cards(apps, schema_editor):
    VoteCard = apps.get_model("core", "VoteCard")
    VoteCard.objects.filter(description="FEEDiT 살말 초기 카드").delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0053_contentitem_ad_disclosure_contentitem_content_format")]

    operations = [
        migrations.CreateModel(
            name="VoteComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content", models.TextField(verbose_name="댓글 내용")),
                ("is_deleted", models.BooleanField(db_index=True, default=False, verbose_name="삭제 여부")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="작성일시")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="수정일시")),
                ("card", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="core.votecard", verbose_name="살말 카드")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="vote_comments", to="core.appuser", verbose_name="작성자")),
            ],
            options={
                "verbose_name": "살말 댓글",
                "verbose_name_plural": "살말 댓글",
                "db_table": '"app"."vote_comment"',
                "indexes": [
                    models.Index(fields=["card", "-created_at"], name="idx_vote_comment_card"),
                    models.Index(fields=["user", "-created_at"], name="idx_vote_comment_user"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="usersaveditem",
            constraint=models.UniqueConstraint(condition=models.Q(("product__isnull", False)), fields=("user", "product"), name="uq_saved_user_product"),
        ),
        migrations.AddConstraint(
            model_name="usersaveditem",
            constraint=models.UniqueConstraint(condition=models.Q(("content_item__isnull", False)), fields=("user", "content_item"), name="uq_saved_user_content"),
        ),
        migrations.RunPython(seed_cards, unseed_cards),
    ]
