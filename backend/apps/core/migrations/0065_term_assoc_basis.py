# 연관어에 근거(basis) 구분 추가 (2026-09-21)
#
#   연관어 출처가 두 갈래가 됐다 — 언급 동시출현(TEXT)과 검색 동시질의(SEARCH).
#   유니크 키에 basis 를 넣지 않으면 같은 용어쌍·같은 날의 두 행이 서로를 덮어쓴다.
#
#   ※ 손으로 쓴 마이그레이션이다. 적용 전에:
#        python manage.py makemigrations core --check --dry-run   → "No changes detected"
#        python manage.py sqlmigrate core 0065
#
#   기존 행은 전부 default="TEXT" 로 채워진다 — 지금까지 만든 연관어가
#   전부 문서 동시출현 기반이니 맞는 값이다.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0064_term_search_trend_region'),
    ]

    operations = [
        # 제약을 먼저 떼고 칼럼을 넣은 뒤 다시 건다 (순서가 바뀌면 충돌한다)
        migrations.RemoveConstraint(
            model_name='termassocdaily',
            name='uq_term_assoc_day_ver',
        ),
        migrations.AddField(
            model_name='termassocdaily',
            name='basis',
            field=models.CharField(
                choices=[('TEXT', '언급 동시출현'), ('SEARCH', '검색 동시질의')],
                default='TEXT', max_length=10, verbose_name='연관 근거',
            ),
        ),
        migrations.AddConstraint(
            model_name='termassocdaily',
            constraint=models.UniqueConstraint(
                fields=('source_term', 'target_term', 'metric_date', 'metric_version', 'basis'),
                name='uq_term_assoc_day_ver_basis',
            ),
        ),
        migrations.AddIndex(
            model_name='termassocdaily',
            index=models.Index(fields=['source_term', 'basis', '-metric_date'],
                               name='idx_assoc_src_basis'),
        ),
    ]
