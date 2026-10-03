"""feedit-chat — 경로와 상수 한 곳.

이 서비스는 **따로 선다.** 크롤러도 Django 도 건드리지 않는다.
나중에 백엔드에 합칠 때 이 파일의 경로만 갈아 끼우면 되도록 모아 뒀다.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # ChatBot/
WORKSPACE = ROOT.parent                            # feedit/ (통합 저장소 루트)

# ── 챗봇이 쓰는 크롤러 코드 · 어휘 추출기 (ChatBot/vendor/) ────────────
#   ★ 2026-09-23 — 저장소 안으로 옮겼다.
#     예전에는 `Final/feedit-crawler` 와 `Final/tools` 를 저장소 **밖**에서
#     import 했다(개발 초기에 챗봇을 Final/feedit-chat 으로 따로 세웠을 때,
#     크롤러 파일을 복사하면 두 곳 판정이 갈릴까 봐 그 자리를 바라보게 했다).
#     그 결과 저장소만 받은 사람은 챗봇 엔진을 띄울 수 없었다.
#
#   vendor/ 에 있는 것 (전부 표준 라이브러리 + PyYAML 만 쓴다):
#     · question_extract.py          질문 어휘 3단 추출 (lexicon_gate 가 import)
#     · feedit_crawler/lexicon.py    Lexicon — SQLite 모드에서만 쓴다
#     · config/lexicon.yaml          어휘 사전 — SQLite 모드에서만 쓴다
#   운영(RDS 모드)에 필요한 건 question_extract.py 하나다.
#
#   SQLite 모드의 지표 DB(data/feedit.db, 약 48MB)와 키 파일(data/keys.json)은
#   저장소에 넣지 않는다. 필요하면 FEEDIT_CHAT_DB 로 가리키거나
#   vendor/data/ 에 두면 된다(.gitignore 처리됨).
#
#   환경변수로 다른 곳을 가리키면 그쪽을 쓴다(예전 설정 호환).
VENDOR = ROOT / "vendor"
CRAWLER = Path(os.getenv("FEEDIT_CRAWLER_DIR") or VENDOR)

# 운영 기본값은 AWS RDS다. SQLite는 회귀 테스트나 오프라인 개발 때만 명시한다.
DATA_BACKEND = os.getenv("FEEDIT_DATA_BACKEND", "rds").strip().lower()
DB_PATH = Path(os.getenv("FEEDIT_CHAT_DB", CRAWLER / "data" / "feedit.db"))
LEXICON_PATH = Path(os.getenv("FEEDIT_CHAT_LEXICON", CRAWLER / "config" / "lexicon.yaml"))

# 어휘 추출기 (검증 완료 — 설계서 3.3)
EXTRACTOR_DIR = Path(os.getenv("FEEDIT_EXTRACTOR_DIR") or VENDOR)

METRIC_VERSION = os.getenv("FEEDIT_METRIC_VERSION", "feedit-unified-text-v1")

# ── "요즘 뜨는 것" 순위의 창 (2026-10-01) ──
#   지표 행은 **언급이 있는 날에만** 생긴다. 예전 순위는 전체 최신일 하루의 행만 봐서,
#   그날 언급되지 않은 용어는 통째로 빠졌다. 스타일은 하루 언급이 1~3건이라 특히 심했다
#   (10/1 실측: 스타일 축 0개 — 클래식 마지막 행 9/30 · 미니멀 9/29 · 고프코어 9/27).
#   최근 이만큼의 날 안에서 용어마다 **마지막 값**으로 줄을 세운다. 그 값은 트렌드 분석
#   화면이 그 용어의 온도로 보여 주는 값과 같다.
RANK_WINDOW_DAYS = max(1, int(os.getenv("FEEDIT_RANK_WINDOW_DAYS") or 7))

# ── 시계열을 말해도 되는 최소 관측 (2026-09-02 실측으로 정한 값) ──
#   최신일 기준 창 안에 관측이 이만큼은 있어야 그 지표를 입에 올린다.
#   실측 결과 — 최신 2026-09-01, term 509개
#       n7>=3   123개    ma7 을 말할 수 있다
#       n14>=5   93개    2주 변화를 말할 수 있다
#       n28>=10  72개    방향(ma7/ma28)을 말할 수 있다
#   축별로는 브랜드가 223개 중 n7>=3 이 2개뿐이다. 브랜드는 방향을 못 말한다.
MIN_OBS_7 = 3
MIN_OBS_14 = 5
MIN_OBS_28 = 10

# 표본이 이보다 적으면 숫자 옆에 경고를 붙인다.
#   트렌드 분석 긍부정 탭의 SENT_MIN_N(최근 28일 반응 20건)과 같은 값이다.
#   ★ 2026-10-01 — 예전엔 이 값을 **하루치** 언급 수에 걸었다. 그러면 거의 모든 용어가
#     '표본 부족' 이 되어, 화면이 '뜨거움' 이라 말하는 용어에 챗봇은 '판단 보류' 라고 했다.
#     지금은 최근 28일 합계에 건다(trend_view.trend_summary · sentiment_summary).
THIN_SAMPLE = 20

# 챗봇이 검색어(주어)로 인정하는 축
SEARCH_FACETS = ("style", "material", "item", "brand")

# 온도 구간 — 트렌드 분석 '언급량·온도' 탭과 같은 경계를 쓴다.
#   frontend/trend/static/js/dispatch.js (id==='temp'):
#       band = temp>=85 ? 과열 : temp>=65 ? 따뜻함 : temp>=40 ? 미지근 : 차가움
#   ★ 2026-10-01 — 예전 경계(25/50/75)는 옛 trend_chat.py 의 것이었다.
#     화면이 '따뜻함(뜨거움)' 이라 말한 아디다스 83° 를 챗봇은 '과열' 이라고 불렀다.
TEMP_BANDS = ((40, "차가움"), (65, "미지근"), (85, "따뜻함"), (101, "과열"))
# 같은 구간의 판정 문구 — 화면 다이얼 옆 제목과 설명 그대로.
TEMP_VERDICTS = {
    "과열": ("과열", "이미 정점을 지나는 신호가 섞여 있습니다. 지금부터는 식는 속도를 지켜볼 구간입니다."),
    "따뜻함": ("뜨거움", "언급량이 꾸준히 오르는 중입니다. 지금 붙잡을 만한 온도입니다."),
    "미지근": ("달아오르는 중", "막 올라오기 시작한 단계입니다. 조금 더 지켜보면 방향이 뚜렷해집니다."),
    "차가움": ("아직 잠잠", "절대 언급량이 적어 판단하기엔 이릅니다. 추적만 걸어두는 편이 안전합니다."),
}


def js_round(value) -> int:
    """JavaScript Math.round 와 같은 반올림(.5 는 위로).

    화면은 Math.round 로 숫자를 띄운다. 파이썬 round() 는 은행가 반올림이라
    82.5 를 82 로 만든다 — 화면 83° 옆에서 챗봇이 82° 라고 말하게 된다.
    """
    import math
    return int(math.floor(float(value) + 0.5))


def missing_inputs() -> list[str]:
    """엔진이 부팅하려면 있어야 하는데 지금 없는 것. 진단용.

    ★ 목록이 비어 있지 않으면 ChatEngine() 은 반드시 실패한다.
      실패한 뒤 스택트레이스를 읽게 하지 않고, 먼저 사람 말로 알려 준다.
    """
    extractor = (EXTRACTOR_DIR / "question_extract.py", "어휘 추출기 (FEEDIT_EXTRACTOR_DIR)")
    if DATA_BACKEND == "rds":
        missing = [name for name in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
                   if not os.getenv(name)]
        out = [f"RDS 환경변수 — {name}" for name in missing]
        if not extractor[0].exists(): out.append(f"{extractor[1]} — {extractor[0]}")
        return out
    need = [
        (DB_PATH, "지표 DB (FEEDIT_CHAT_DB)"),
        (LEXICON_PATH, "어휘 사전 (FEEDIT_CHAT_LEXICON)"), extractor,
        (CRAWLER / "feedit_crawler" / "lexicon.py", "크롤러 Lexicon (FEEDIT_CRAWLER_DIR)"),
    ]
    return [f"{label} — {path}" for path, label in need if not path.exists()]


def temp_band(value) -> str:
    # 화면은 반올림한 정수로 구간을 정한다(84.6 → 85 → 과열). 같은 순서로 한다.
    v = js_round(value or 0)
    for edge, name in TEMP_BANDS:
        if v < edge:
            return name
    return "과열"
