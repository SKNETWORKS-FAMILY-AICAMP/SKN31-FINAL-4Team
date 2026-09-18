from analysis.product_enrichment.pipeline import (
    ProductEnrichmentPipeline,
)


def run_smoke(
    *,
    source_code="ZIGZAG",
    limit=10,
    force=True,
    persist_unknown=False,
):
    pipeline = ProductEnrichmentPipeline(
        source_code=source_code
    )

    return pipeline.run(
        limit=limit,
        force=force,
        persist_known=True,
        persist_unknown=persist_unknown,
        cnv_candidates_only=True,
    )
