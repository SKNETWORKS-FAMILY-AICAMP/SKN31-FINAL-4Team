"""YouTube 댓글 · 커머스 리뷰 · 콘텐츠 본문(영상 제목+설명)을 같은 방식으로 분석하는 텍스트 신호 파이프라인."""


def run_text_signal_pipeline(*args, **kwargs):
    from .service import run_text_signal_pipeline as implementation
    return implementation(*args, **kwargs)


def sync_product_reviews(*args, **kwargs):
    from .service import sync_product_reviews as implementation
    return implementation(*args, **kwargs)


def sync_content_documents(*args, **kwargs):
    from .service import sync_content_documents as implementation
    return implementation(*args, **kwargs)


__all__ = ["run_text_signal_pipeline", "sync_product_reviews", "sync_content_documents"]