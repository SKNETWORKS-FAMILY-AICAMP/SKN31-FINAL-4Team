import math
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import (
    DictionaryTerm,
    TermAlias,
    TextDocument,
    TextTermMention,
    ProductSource,
    ProductTerm,
    ContentItem,
    TermAssocDaily,
)


def _norm(s):
    return "".join(str(s or "").split()).lower()

def _tag_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _tag_values(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not str(key).startswith("_"):
                yield from _tag_values(item)

class Command(BaseCommand):
    help = "Backfill TermAssocDaily using mentions, products, and content tags"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Do not save to DB")
        parser.add_argument("--date", type=str, help="YYYY-MM-DD for metric_date (default: today)")
        parser.add_argument("--limit-per-term", type=int, default=50, help="Max associations per source term")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        metric_version = "feedit-l2-v1"

        date_str = options.get("date")
        if date_str:
            metric_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            metric_date = timezone.localdate()

        self.stdout.write(f"Starting backfill for date {metric_date} (dry-run: {dry_run})")

        # 1. Load active terms and mapping
        self.stdout.write("Loading terms...")
        terms = list(DictionaryTerm.objects.exclude(status="INACTIVE").values("id", "canonical_name", "normalized_name", "term_type"))
        by_id = {row["id"]: row for row in terms}
        by_name = {}
        for row in terms:
            for value in (row["canonical_name"], row["normalized_name"]):
                key = _norm(value)
                if key:
                    by_name.setdefault(key, row["id"])

        for alias in TermAlias.objects.filter(term_id__in=by_id).values("term_id", "alias", "normalized_alias"):
            for value in (alias["alias"], alias["normalized_alias"]):
                key = _norm(value)
                if key:
                    by_name.setdefault(key, alias["term_id"])

        active_term_ids = set(by_id.keys())
        self.stdout.write(f"Loaded {len(active_term_ids)} active terms.")

        # 2. Extract relationships
        # record_id -> set of term_ids
        doc_terms = defaultdict(set)
        prod_terms = defaultdict(set)
        content_terms = defaultdict(set)

        self.stdout.write("Loading TextTermMention...")
        for row in TextTermMention.objects.values("document_id", "term_id").iterator(chunk_size=5000):
            if row["term_id"] in active_term_ids:
                doc_terms[row["document_id"]].add(row["term_id"])

        self.stdout.write("Loading ProductTerm & Style...")
        for row in ProductTerm.objects.values("product_source_id", "term_id").iterator(chunk_size=5000):
            if row["term_id"] in active_term_ids:
                prod_terms[row["product_source_id"]].add(row["term_id"])

        # ★ 2026-09-21 — 예전에는 표준 상품의 단일 스타일 FK(product.style) 를 한 번 더 긁었다.
        #   스타일이 여러 개 달릴 수 있게 바뀌면서 그 칸은 없어졌고, 위 ProductTerm 루프가
        #   스타일까지 모두 포함한다.

        self.stdout.write("Loading ContentItem.analysis_tags...")
        for row in ContentItem.objects.exclude(analysis_tags={}).values("id", "analysis_tags").iterator(chunk_size=2000):
            ids = {by_name[key] for raw in _tag_values(row["analysis_tags"]) if (key := _norm(raw)) in by_name}
            for tid in ids:
                content_terms[row["id"]].add(tid)

        # 3. Calculate N and N(A)
        # We only consider records that have at least one valid term (or total universe? Let's use universe of valid docs)
        N_doc = TextDocument.objects.count()
        N_prod = ProductSource.objects.count()
        N_content = ContentItem.objects.exclude(analysis_tags={}).count()
        N = N_doc + N_prod + N_content
        if N == 0:
            self.stdout.write("N is 0, nothing to do.")
            return

        term_counts = defaultdict(int)
        for d_set in doc_terms.values():
            for t in d_set: term_counts[t] += 1
        for p_set in prod_terms.values():
            for t in p_set: term_counts[t] += 1
        for c_set in content_terms.values():
            for t in c_set: term_counts[t] += 1

        # 4. Calculate N(A, B)
        cooc = defaultdict(lambda: defaultdict(int))

        def add_cooc(t_set):
            t_list = list(t_set)
            for i in range(len(t_list)):
                for j in range(i+1, len(t_list)):
                    t1, t2 = t_list[i], t_list[j]
                    cooc[t1][t2] += 1
                    cooc[t2][t1] += 1

        for d_set in doc_terms.values(): add_cooc(d_set)
        for p_set in prod_terms.values(): add_cooc(p_set)
        for c_set in content_terms.values(): add_cooc(c_set)

        # 5. Compute Lift and PMI and Rank
        self.stdout.write(f"Total N = {N}. Calculating Lift and PMI...")

        records_to_save = []
        for source_id, targets in cooc.items():
            n_A = term_counts[source_id]
            if n_A == 0: continue

            scored_targets = []
            for target_id, n_AB in targets.items():
                n_B = term_counts[target_id]
                if n_B == 0: continue

                # lift = N * n(A,B) / (n(A) * n(B))
                lift = (N * n_AB) / (n_A * n_B)
                # pmi = log2(lift)
                pmi = math.log2(lift) if lift > 0 else 0

                scored_targets.append((target_id, n_AB, lift, pmi))

            # Sort by PMI desc, then cooc desc
            scored_targets.sort(key=lambda x: (x[3], x[1]), reverse=True)

            for rank, (target_id, n_AB, lift, pmi) in enumerate(scored_targets[:options["limit_per_term"]], 1):
                records_to_save.append(TermAssocDaily(
                    source_term_id=source_id,
                    target_term_id=target_id,
                    metric_date=metric_date,
                    metric_version=metric_version,
                    cooccurrence_count=n_AB,
                    lift=lift,
                    pmi=pmi,
                    association_rank=rank,
                    # We skip association_percentile and is_new for now
                ))

        self.stdout.write(f"Calculated {len(records_to_save)} association records.")

        if dry_run:
            self.stdout.write("Dry run finished. Not saving to DB.")
            if records_to_save:
                sample = records_to_save[0]
                self.stdout.write(f"Sample: {sample.source_term_id} -> {sample.target_term_id} (Cooc: {sample.cooccurrence_count}, Lift: {sample.lift:.2f}, PMI: {sample.pmi:.2f})")
            return

        self.stdout.write("Saving to DB...")

        with transaction.atomic():
            # Delete existing records for this date and version
            TermAssocDaily.objects.filter(metric_date=metric_date, metric_version=metric_version).delete()

            # Bulk create
            TermAssocDaily.objects.bulk_create(records_to_save, batch_size=2000)

        self.stdout.write(self.style.SUCCESS(f"Successfully saved {len(records_to_save)} TermAssocDaily records."))
