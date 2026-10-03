# 검색 지표 표 추가 (2026-09-21)
#
#   ① Source 에 SEARCH 타입 — 네이버·구글은 커머스도 콘텐츠도 아니다.
#   ② term_search_metric_monthly 에 PC/모바일/광고경쟁도 칸 (네이버 검색광고 N1·N4)
#   ③ analysis.term_search_trend   — 검색 관심도 시계열 (D1·D2·D3·G1)
#   ④ analysis.term_search_region  — 시·도별 검색 관심도 (G5)
#
#   ※ 손으로 쓴 마이그레이션이다. 적용 전에 아래 두 줄로 반드시 확인할 것:
#        python manage.py makemigrations core --check --dry-run   → "No changes detected"
#        python manage.py sqlmigrate core 0064                    → 나갈 SQL 미리보기

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0063_drop_product_style_fk'),
    ]

    operations = [
        migrations.AlterField(
            model_name='source',
            name='source_type',
            field=models.CharField(
                choices=[('COMMERCE', 'Commerce'), ('CONTENT', 'Content'), ('SEARCH', 'Search')],
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name='termsearchmetricmonthly',
            name='pc_volume',
            field=models.BigIntegerField(blank=True, null=True, verbose_name='PC 검색량'),
        ),
        migrations.AddField(
            model_name='termsearchmetricmonthly',
            name='mobile_volume',
            field=models.BigIntegerField(blank=True, null=True, verbose_name='모바일 검색량'),
        ),
        migrations.AddField(
            model_name='termsearchmetricmonthly',
            name='competition',
            field=models.CharField(
                blank=True, max_length=20, null=True,
                help_text="네이버 검색광고 기준 높음/중간/낮음. '시장 포화도'가 아니라 광고 경쟁 강도다.",
                verbose_name='광고 경쟁도',
            ),
        ),
        migrations.CreateModel(
            name='TermSearchTrend',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metric_date', models.DateField(help_text='주간이면 그 주의 시작일, 월간이면 1일.', verbose_name='구간 시작일')),
                ('time_unit', models.CharField(choices=[('DAY', '일간'), ('WEEK', '주간'), ('MONTH', '월간')], default='WEEK', max_length=10)),
                ('segment', models.CharField(default='all', max_length=20, verbose_name='세그먼트')),
                ('ratio', models.DecimalField(blank=True, decimal_places=3, max_digits=7, null=True, verbose_name='상대 지수 (0~100)')),
                ('estimated_volume', models.BigIntegerField(blank=True, null=True, verbose_name='추정 절대 검색량')),
                ('metric_version', models.CharField(default='feedit-search-v1', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='term_search_trend', to='core.source', verbose_name='검색 플랫폼')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='search_trend', to='core.dictionaryterm', verbose_name='용어')),
            ],
            options={
                'db_table': '"analysis"."term_search_trend"',
            },
        ),
        migrations.CreateModel(
            name='TermSearchRegion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metric_date', models.DateField(verbose_name='수집 기준일')),
                ('region', models.CharField(max_length=40, verbose_name='시·도')),
                ('value', models.IntegerField(default=0, verbose_name='지역 관심도 (0~100)')),
                ('metric_version', models.CharField(default='feedit-search-v1', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='term_search_region', to='core.source', verbose_name='검색 플랫폼')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='search_region', to='core.dictionaryterm', verbose_name='용어')),
            ],
            options={
                'db_table': '"analysis"."term_search_region"',
            },
        ),
        migrations.AddIndex(
            model_name='termsearchtrend',
            index=models.Index(fields=['term', '-metric_date'], name='idx_strend_term_date'),
        ),
        migrations.AddIndex(
            model_name='termsearchtrend',
            index=models.Index(fields=['source', '-metric_date'], name='idx_strend_src_date'),
        ),
        migrations.AddIndex(
            model_name='termsearchtrend',
            index=models.Index(fields=['segment'], name='idx_strend_segment'),
        ),
        migrations.AddConstraint(
            model_name='termsearchtrend',
            constraint=models.UniqueConstraint(
                fields=('term', 'source', 'metric_date', 'time_unit', 'segment', 'metric_version'),
                name='uq_term_search_trend',
            ),
        ),
        migrations.AddIndex(
            model_name='termsearchregion',
            index=models.Index(fields=['term', '-metric_date'], name='idx_sregion_term_date'),
        ),
        migrations.AddIndex(
            model_name='termsearchregion',
            index=models.Index(fields=['region', '-value'], name='idx_sregion_value'),
        ),
        migrations.AddConstraint(
            model_name='termsearchregion',
            constraint=models.UniqueConstraint(
                fields=('term', 'source', 'metric_date', 'region', 'metric_version'),
                name='uq_term_search_region',
            ),
        ),
    ]
