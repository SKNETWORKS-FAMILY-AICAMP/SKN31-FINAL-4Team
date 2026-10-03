from __future__ import annotations

# ============================================================
# DJANGO BOOTSTRAP
#
# 반드시 프로젝트 모듈 import보다 먼저 실행되어야 한다.
# ============================================================

import os

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

import django

django.setup()


# ============================================================
# IMPORTS
# ============================================================

import argparse
import shutil
from pathlib import Path

from pipeline.step02_normalization.semantic_tokenizer.corpus_generator import (
    FeedItCorpusGenerator,
)

from pipeline.step02_normalization.semantic_tokenizer.train_sentencepiece import (
    REGRESSION_TEXTS,
    evaluate_model,
    print_per_text_comparison,
    print_summary,
    save_report,
    train_one,
)

from pipeline.step02_normalization.semantic_tokenizer.sync_brand_dictionary import (
    sync_brand_dictionary,
)

from pipeline.step02_normalization.semantic_tokenizer.tokenizer import (
    reload_tokenizer_dictionary,
)


# ============================================================
# PATHS
# ============================================================

THIS_DIR = Path(__file__).resolve().parent

CORPUS_DIR = (
    THIS_DIR
    / "data"
    / "corpora"
)

MODEL_DIR = (
    THIS_DIR
    / "data"
    / "sentencepiece"
)

DEFAULT_CORPUS_PATH = (
    CORPUS_DIR
    / "feedit_product_corpus_v4.txt"
)

CURRENT_MODEL_PATH = (
    MODEL_DIR
    / "feedit_spm_current.model"
)

CURRENT_VOCAB_PATH = (
    MODEL_DIR
    / "feedit_spm_current.vocab"
)


# ============================================================
# BRAND DICTIONARY SYNC
# ============================================================

def run_brand_sync() -> None:

    print()
    print("=" * 100)
    print("1. BRAND DICTIONARY SYNC")
    print("=" * 100)

    result = sync_brand_dictionary()

    if result is not None:
        print(
            "RESULT:",
            result,
        )

    print()
    print("BRAND DICTIONARY SYNC DONE")


# ============================================================
# TOKENIZER DICTIONARY RELOAD
# ============================================================

def run_dictionary_reload() -> None:

    print()
    print("=" * 100)
    print("2. TOKENIZER DICTIONARY RELOAD")
    print("=" * 100)

    reload_tokenizer_dictionary()

    print(
        "TOKENIZER DICTIONARY RELOADED"
    )


# ============================================================
# CORPUS GENERATION
# ============================================================

def run_corpus_generation(
    *,
    corpus_path: Path,
    limit: int | None = None,
) -> dict:

    print()
    print("=" * 100)
    print("3. CORPUS GENERATION")
    print("=" * 100)

    print(
        "OUTPUT:",
        corpus_path,
    )

    generator = FeedItCorpusGenerator(
        output_path=corpus_path,

        # Dictionary canonical
        canonical_weight=5,

        # Dictionary aliases
        alias_weight=3,

        # Compound/reusable concepts
        compound_weight=8,

        # Brand / BrandSource names
        brand_weight=6,
    )

    stats = generator.generate(
        limit=limit,
        include_dictionary=True,
    )

    stats_dict = stats.to_dict()

    print()
    print("-" * 100)
    print("CORPUS STATS")
    print("-" * 100)

    for key, value in stats_dict.items():

        print(
            f"{key:<24}:",
            value,
        )

    print()
    print(
        "CORPUS PATH:",
        corpus_path,
    )

    return stats_dict


# ============================================================
# SENTENCEPIECE TRAIN
# ============================================================

def run_training(
    *,
    corpus_path: Path,
    vocab_size: int,
    version: str,
    model_type: str,
) -> Path:

    print()
    print("=" * 100)
    print("4. SENTENCEPIECE TRAINING")
    print("=" * 100)

    print(
        "VOCAB SIZE:",
        vocab_size,
    )

    print(
        "VERSION   :",
        version,
    )

    print(
        "MODEL TYPE:",
        model_type,
    )

    model_path = train_one(
        corpus_path=corpus_path,
        output_dir=MODEL_DIR,
        vocab_size=vocab_size,
        version=version,
        model_type=model_type,
    )

    return model_path


# ============================================================
# REGRESSION TEST
# ============================================================

def run_regression(
    *,
    model_path: Path,
    version: str,
) -> dict:

    print()
    print("=" * 100)
    print("5. REGRESSION TEST")
    print("=" * 100)

    evaluation = evaluate_model(
        model_path=model_path,
        texts=REGRESSION_TEXTS,
    )

    evaluations = [
        evaluation,
    ]

    print_summary(
        evaluations,
    )

    print_per_text_comparison(
        evaluations,
    )

    save_report(
        evaluations=evaluations,
        output_dir=MODEL_DIR,
        version=version,
    )

    return evaluation


# ============================================================
# CURRENT MODEL PROMOTION
# ============================================================

def promote_current_model(
    *,
    model_path: Path,
) -> None:

    print()
    print("=" * 100)
    print("6. PROMOTE CURRENT MODEL")
    print("=" * 100)

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    vocab_path = model_path.with_suffix(
        ".vocab"
    )

    if not model_path.exists():

        raise FileNotFoundError(
            f"Model not found: {model_path}"
        )

    shutil.copy2(
        model_path,
        CURRENT_MODEL_PATH,
    )

    print(
        "CURRENT MODEL:",
        CURRENT_MODEL_PATH,
    )

    if vocab_path.exists():

        shutil.copy2(
            vocab_path,
            CURRENT_VOCAB_PATH,
        )

        print(
            "CURRENT VOCAB:",
            CURRENT_VOCAB_PATH,
        )


# ============================================================
# FINAL SMOKE TEST
# ============================================================

def run_smoke_test(
    *,
    model_path: Path,
) -> None:

    print()
    print("=" * 100)
    print("7. FINAL SMOKE TEST")
    print("=" * 100)

    import sentencepiece as spm

    processor = (
        spm.SentencePieceProcessor()
    )

    processor.load(
        str(model_path)
    )

    texts = [
        "나이키 에어맥스 블랙",
        "아디다스 오버핏 후드",
        "살로몬 고프코어 스니커즈",
        "발레코어 리본 가디건",
        "단색 레귤러핏 니트",
    ]

    for text in texts:

        pieces = processor.encode(
            text,
            out_type=str,
        )

        print()
        print(
            "TEXT  :",
            text,
        )

        print(
            "PIECES:",
            pieces,
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "FEEDIT semantic tokenizer "
            "dictionary sync + corpus generation "
            "+ SentencePiece retraining"
        )
    )

    parser.add_argument(
        "--vocab-size",
        type=int,
        default=12000,
    )

    parser.add_argument(
        "--version",
        type=str,
        default="v4",
    )

    parser.add_argument(
        "--model-type",
        choices=[
            "unigram",
            "bpe",
        ],
        default="unigram",
    )

    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS_PATH,
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "상품명 corpus 개수 제한. "
            "기본값 None이면 전체 상품 사용."
        ),
    )

    parser.add_argument(
        "--skip-brand-sync",
        action="store_true",
    )

    parser.add_argument(
        "--skip-train",
        action="store_true",
    )

    args = parser.parse_args()


    print()
    print("=" * 100)
    print("FEEDIT SEMANTIC TOKENIZER RETRAIN")
    print("=" * 100)

    print(
        "CORPUS SIZE LIMIT:",
        args.limit or "ALL",
    )

    print(
        "VOCAB SIZE       :",
        args.vocab_size,
    )

    print(
        "VERSION          :",
        args.version,
    )


    # ========================================================
    # 1. Brand -> DictionaryTerm(BRAND)
    # ========================================================

    if not args.skip_brand_sync:

        run_brand_sync()

    else:

        print()
        print(
            "BRAND SYNC SKIPPED"
        )


    # ========================================================
    # 2. Dictionary matcher reload
    # ========================================================

    run_dictionary_reload()


    # ========================================================
    # 3. Corpus
    # ========================================================

    run_corpus_generation(
        corpus_path=args.corpus,
        limit=args.limit,
    )


    # ========================================================
    # 4. Train
    # ========================================================

    expected_model_path = (
        MODEL_DIR
        / (
            f"feedit_spm_"
            f"{args.vocab_size // 1000}k_"
            f"{args.version}.model"
        )
    )

    if args.skip_train:

        print()
        print(
            "TRAINING SKIPPED"
        )

        if not expected_model_path.exists():

            raise FileNotFoundError(
                "skip-train을 사용했지만 "
                f"모델이 없습니다: "
                f"{expected_model_path}"
            )

        model_path = (
            expected_model_path
        )

    else:

        model_path = run_training(
            corpus_path=args.corpus,
            vocab_size=args.vocab_size,
            version=args.version,
            model_type=args.model_type,
        )


    # ========================================================
    # 5. Regression
    # ========================================================

    run_regression(
        model_path=model_path,
        version=args.version,
    )


    # ========================================================
    # 6. Promote
    # ========================================================

    promote_current_model(
        model_path=model_path,
    )


    # ========================================================
    # 7. Smoke test
    # ========================================================

    run_smoke_test(
        model_path=CURRENT_MODEL_PATH,
    )


    # ========================================================
    # FINAL
    # ========================================================

    print()
    print("=" * 100)
    print("RETRAIN COMPLETE")
    print("=" * 100)

    print(
        "CORPUS:",
        args.corpus,
    )

    print(
        "MODEL :",
        model_path,
    )

    print(
        "CURRENT:",
        CURRENT_MODEL_PATH,
    )


if __name__ == "__main__":
    main()