from __future__ import annotations

import argparse
import json
from pathlib import Path

import sentencepiece as spm


THIS_DIR = Path(__file__).resolve().parent

DEFAULT_CORPUS = (
    THIS_DIR
    / "data"
    / "corpora"
    / "feedit_product_corpus_v2.txt"
)

DEFAULT_OUTPUT_DIR = (
    THIS_DIR
    / "data"
    / "sentencepiece"
)

DEFAULT_VOCAB_SIZES = (
    8000,
    12000,
    16000,
)

DEFAULT_VERSION = "v3"


REGRESSION_TEXTS = [
    "다운타운 그래픽 티 - 블랙",
    "파리 스탠다드 코튼 셔츠",
    "시티 레저 벨티드 유틸리티 쇼츠",
    "플랫폼 도트 스니커즈 블랙",
    "플랩 코튼 자켓",
    "우먼즈 에센셜 부츠 컷 데님 팬츠",
    "로프 와이드 데님팬츠",
    "반소매 셔츠",
    "MUSE STRIPE POLO KNIT MELANGE GRAY",
    "DOODLE HEART HALF T WHITE GREYISH BLUE",
    "CUT OFF SLUB LONG SLEEVE CHARCOAL",
    "V거셋 포켓 데님 맨투맨",
    "COOLMAX 반팔 티셔츠",
    "빈티지플라워새틴롱SK",
    "히든 밴딩 슬랙스",
    "레더 라이더스 재킷",
    "크로셰 니트",
    "맥시 원피스",
    "미니 원피스",
    "조거 팬츠",
]


def train_one(
    *,
    corpus_path: Path,
    output_dir: Path,
    vocab_size: int,
    version: str,
    model_type: str = "unigram",
) -> Path:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not corpus_path.exists():
        raise FileNotFoundError(
            f"Corpus not found: {corpus_path}"
        )

    model_prefix = (
        output_dir
        / f"feedit_spm_{vocab_size // 1000}k_{version}"
    )

    print()
    print("=" * 100)
    print(
        f"TRAINING FEEDIT SPM "
        f"{vocab_size:,} / {version}"
    )
    print("=" * 100)

    spm.SentencePieceTrainer.train(
        input=str(corpus_path),
        model_prefix=str(model_prefix),

        # ==================================================
        # MODEL
        # ==================================================
        model_type=model_type,
        vocab_size=vocab_size,
        character_coverage=1.0,
        hard_vocab_limit=False,

        # ==================================================
        # NORMALIZATION
        # ==================================================
        normalization_rule_name="nfkc",

        # ==================================================
        # FEEDIT v3
        #
        # 핵심:
        # 상품명 전체를 하나의 piece로 외우는 현상을 줄인다.
        #
        # "파리 스탠다드 코튼 셔츠"
        # "히든 밴딩 슬랙스"
        # 같은 문장을 통째로 piece로 만드는 것을 방지.
        # ==================================================
        split_by_whitespace=True,

        split_by_number=True,
        split_digits=False,

        # 지나치게 긴 phrase 암기 방지
        max_sentencepiece_length=16,

        allow_whitespace_only_pieces=False,

        # ==================================================
        # SPECIAL TOKENS
        # ==================================================
        unk_id=0,
        bos_id=-1,
        eos_id=-1,
        pad_id=-1,
        unk_piece="<unk>",

        # ==================================================
        # TRAINING
        # ==================================================
        num_threads=8,
        shuffle_input_sentence=True,
        input_sentence_size=1_000_000,
        train_extremely_large_corpus=False,
    )

    model_path = Path(
        str(model_prefix) + ".model"
    )

    print(
        "MODEL:",
        model_path,
    )

    print(
        "VOCAB:",
        str(model_prefix) + ".vocab",
    )

    return model_path


def load_processor(
    model_path: Path,
) -> spm.SentencePieceProcessor:

    processor = (
        spm.SentencePieceProcessor()
    )

    processor.load(
        str(model_path)
    )

    return processor


def evaluate_model(
    *,
    model_path: Path,
    texts: list[str],
) -> dict:

    processor = load_processor(
        model_path
    )

    rows = []

    piece_counts = []

    for text in texts:

        pieces = processor.encode(
            text,
            out_type=str,
        )

        piece_counts.append(
            len(pieces)
        )

        rows.append({
            "text": text,
            "piece_count": len(pieces),
            "pieces": pieces,
        })

    avg_piece_count = (
        sum(piece_counts)
        / len(piece_counts)
        if piece_counts
        else 0.0
    )

    return {
        "model": str(model_path),
        "avg_piece_count": round(
            avg_piece_count,
            3,
        ),
        "min_piece_count": min(
            piece_counts,
            default=0,
        ),
        "max_piece_count": max(
            piece_counts,
            default=0,
        ),
        "rows": rows,
    }


def print_summary(
    evaluations: list[dict],
) -> None:

    print()
    print("=" * 100)
    print("FEEDIT SPM REGRESSION SUMMARY")
    print("=" * 100)

    for result in evaluations:

        model_name = Path(
            result["model"]
        ).name

        print(
            f"{model_name:<34}"
            f"AVG={result['avg_piece_count']:<7}"
            f"MIN={result['min_piece_count']:<4}"
            f"MAX={result['max_piece_count']:<4}"
        )


def print_per_text_comparison(
    evaluations: list[dict],
) -> None:

    if not evaluations:
        return

    print()
    print("=" * 100)
    print("PER-TEXT COMPARISON")
    print("=" * 100)

    count = len(
        evaluations[0]["rows"]
    )

    for index in range(count):

        text = (
            evaluations[0]
            ["rows"][index]
            ["text"]
        )

        print()
        print("-" * 100)
        print(text)

        for result in evaluations:

            model_name = Path(
                result["model"]
            ).stem

            row = (
                result["rows"][index]
            )

            print(
                f"{model_name}: "
                f"{row['piece_count']} pieces"
            )

            print(
                "  ",
                row["pieces"],
            )


def save_report(
    *,
    evaluations: list[dict],
    output_dir: Path,
    version: str,
) -> Path:

    report_path = (
        output_dir
        / f"feedit_spm_{version}_comparison.json"
    )

    with report_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            evaluations,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        "REPORT:",
        report_path,
    )

    return report_path


def parse_vocab_sizes(
    raw: str,
) -> tuple[int, ...]:

    values = []

    for value in raw.split(","):

        value = value.strip()

        if not value:
            continue

        values.append(
            int(value)
        )

    if not values:
        raise ValueError(
            "vocab size가 비어 있습니다."
        )

    return tuple(values)


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Train FEEDIT SentencePiece v3 "
            "models and compare regressions."
        )
    )

    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    parser.add_argument(
        "--vocab-sizes",
        type=str,
        default="8000,12000,16000",
    )

    parser.add_argument(
        "--version",
        type=str,
        default=DEFAULT_VERSION,
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
        "--skip-train",
        action="store_true",
        help=(
            "이미 생성된 model을 사용해 "
            "regression 비교만 수행"
        ),
    )

    args = parser.parse_args()

    vocab_sizes = parse_vocab_sizes(
        args.vocab_sizes
    )

    model_paths = []

    for vocab_size in vocab_sizes:

        expected_path = (
            args.output_dir
            / (
                f"feedit_spm_"
                f"{vocab_size // 1000}k_"
                f"{args.version}.model"
            )
        )

        if args.skip_train:

            if expected_path.exists():

                model_paths.append(
                    expected_path
                )

            else:

                print(
                    "MISSING:",
                    expected_path,
                )

            continue

        model_path = train_one(
            corpus_path=args.corpus,
            output_dir=args.output_dir,
            vocab_size=vocab_size,
            version=args.version,
            model_type=args.model_type,
        )

        model_paths.append(
            model_path
        )

    evaluations = [
        evaluate_model(
            model_path=model_path,
            texts=REGRESSION_TEXTS,
        )
        for model_path in model_paths
    ]

    print_summary(
        evaluations
    )

    print_per_text_comparison(
        evaluations
    )

    save_report(
        evaluations=evaluations,
        output_dir=args.output_dir,
        version=args.version,
    )


if __name__ == "__main__":
    main()
