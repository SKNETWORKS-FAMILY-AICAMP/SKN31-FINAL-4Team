"""준비된 FEEDiT 모델과 여러 상품 사진을 GPT Image 2.5 (Sunburst · Flare)에 보낸다."""
from __future__ import annotations

import base64
import contextlib
import os
import random
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "assets" / "vton_models"
# ── 모델 사진 ────────────────────────────────────────────────
#   <id>/master/ 기준 사진 여섯 장 · <id>/poses/ 자세 여러 장.
MODELS = {
    # who — 프롬프트가 결과 인물의 성별을 못 박을 때 쓴다(2026-10-02, prompt() 의 who).
    "woman": {"label": "여성 모델", "who": "여성", "dir": MODEL_DIR / "woman"},
    "man": {"label": "남성 모델", "who": "남성", "dir": MODEL_DIR / "man"},
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MASTER_DIR = "master"
POSE_DIR = "poses"
# ── 기준 사진 (2026-09-14) ──────────────────────────────────
#   왜 여섯 장이나 보내나 —
#     포즈 한 장만 보내면 그 한 장에 안 보이는 것은 모델이 지어낸다. 옆모습이
#     조금만 돌아가도 얼굴이 딴사람이 되고, 어깨너비와 다리 길이가 컷마다
#     달라졌다. 얼굴 셋(정면·좌45·우45)과 전신 셋(정면·측면·후면)을 같이 보내면
#     "이 사람은 어느 각도에서 이렇게 생겼다" 가 닫힌다 — 옷만 갈아입는 그림이 된다.
#   ★ 순서가 곧 프롬프트의 번호다. 파일 이름 앞의 01~06 이 그 순서를 잡는다 —
#     이름을 바꾸면 프롬프트가 가리키는 번호가 어긋난다(prompt() 주석 참고).
MASTER_COUNT = 6
REFERENCE_COUNT = MASTER_COUNT + 1          # 마스터 6 + 이번 컷의 포즈 1
# API 가 한 번에 받는 이미지 수. 기준 사진이 이 중 앞자리를 미리 쓴다.
MAX_IMAGES = 16


def _missing(model_id: str, folder: str, what: str, extra: str = "") -> str:
    """★ 무엇이 어디에 없는지까지 말한다 (2026-09-14).

    예전에는 어느 경우든 "선택한 AI 모델을 찾을 수 없습니다." 한 줄이었다.
    사진 폴더를 옮긴 뒤 옛 코드를 물고 있던 서버가 이 문구를 뱉었는데, 화면만
    봐서는 모델 이름이 틀린 건지 파일이 없는 건지 서버가 낡은 건지 알 수 없었다.
    """
    model = MODELS.get(model_id)
    label = model["label"] if model else model_id
    where = f"assets/vton_models/{model_id}/{folder}"
    tail = f" ({extra})" if extra else ""
    return (f"{label}의 {what}이 없습니다{tail} — {where} 를 확인하고, "
            f"사진을 옮겼다면 챗봇 서버를 다시 시작하세요.")


def _images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.iterdir()
                  if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)


def masters(model_id: str) -> list[Path]:
    """얼굴 셋 + 전신 셋. 이름순이 곧 프롬프트가 부르는 순서다."""
    model = MODELS.get(model_id)
    return _images(model["dir"] / MASTER_DIR) if model else []


def poses(model_id: str) -> list[Path]:
    """이 모델로 쓸 수 있는 자세들."""
    model = MODELS.get(model_id)
    return _images(model["dir"] / POSE_DIR) if model else []


def pick_pose(model_id: str, pose: str | None = None) -> Path:
    """포즈 하나를 고른다. 이름을 콕 집어 주면 그것, 아니면 무작위.

    ★ 고른 결과를 화면에 돌려준다(generate 의 pose) — "왜 자세가 바뀌었나"
      하고 물었을 때 답할 수 있어야 한다.
    """
    found = poses(model_id)
    if not found:
        raise ValueError(_missing(model_id, POSE_DIR, "포즈 사진"))
    if pose:
        for path in found:
            if path.name == pose:
                return path
    return random.choice(found)


def references(model_id: str, pose: str | None = None) -> list[Path]:
    """모델에 대해 보낼 사진 전부 — 마스터 여섯 장 다음에 이번 컷의 포즈 한 장."""
    found = masters(model_id)
    if len(found) != MASTER_COUNT:
        raise ValueError(_missing(model_id, MASTER_DIR,
                                  f"기준 사진 {MASTER_COUNT}장",
                                  f"지금 {len(found)}장"))
    return found + [pick_pose(model_id, pose)]


# ── 착장 칸 (2026-09-14: 모자·벨트·안경 추가) ────────────────
#   ★ 순서가 곧 화면의 칸 순서다. 프론트(VF_CATEGORIES)와 같은 순서를 쓴다 —
#     한쪽만 늘리면 화면의 드롭다운과 서버가 아는 칸이 어긋난다.
SLOT_ORDER = ["상의", "하의", "아우터", "원피스(셋업)", "신발", "양말",
              "모자", "벨트", "안경"]
AUTO = "자동 분류"
CATEGORIES = set(SLOT_ORDER) | {AUTO}
# ── 생성 엔진 (2026-10-01) ──────────────────────────────────
#   사용자가 고른다. 기본은 화질 쪽(Sunburst), 빨리 보고 싶으면 Flare.
#   OpenAI 문서(2026-10-01 확인, developers.openai.com · GPT Image 2.5 prompting guide):
#     Sunburst — "optimized for quality", GPT Image 2 보다 높은 화질
#     Flare    — "optimized for speed", GPT Image 2 와 비슷한 화질
#     두 모델 모두 images/edits 를 받고, 해상도 한도(긴 변 3840 · 픽셀 8,294,400)와
#     quality 값(low … max)이 같다 — 그래서 SIZE · QUALITY 를 따로 두지 않는다.
#   ★ 얼마나 빨라지는지는 우리 입력(기준 사진 7장 + 상품)으로 재 봐야 안다.
#     결과의 elapsed_ms 로 남긴다. 문서도 "자기 작업으로 재라" 고 적어 두었다.
ENGINES = {
    "sunburst": {"model": "gpt-image-2.5-sunburst", "label": "GPT Image 2.5 Sunburst"},
    "flare": {"model": "gpt-image-2.5-flare", "label": "GPT Image 2.5 Flare"},
}
DEFAULT_ENGINE = "sunburst"
MODEL = ENGINES[DEFAULT_ENGINE]["model"]


def engine_of(name: str | None) -> str:
    """모르는 이름은 기본 엔진으로 — 옛 화면은 engine 을 보내지 않는다."""
    key = str(name or "").strip().lower()
    return key if key in ENGINES else DEFAULT_ENGINE
# ── 출력 해상도·품질 (2026-09-14) ───────────────────────────
#   1024x1024(정사각, 기본 품질)로 내던 것을 4K급 세로로 올린다.
#   ★ 왜 3840x2160(표준 4K)이 아니라 2480x3312 인가 —
#     모델 사진이 3:4 세로다. 가로 4K 로 내면 전신이 가운데 조금만 남고,
#     세로 4K(2160x3840, 9:16)로 내면 사진보다 훨씬 좁고 길어 양옆이 잘린다.
#     같은 3:4 를 유지한 채 Sunburst 가 받아 주는 한계까지 키운 값이 이것이다.
#   ★ API 제약 (images/edits): 두 변 모두 16의 배수, 긴 변 ≤ 3840px,
#     총 픽셀 ≤ 8,294,400, 가로세로비 1:3 ~ 3:1.
#       2480 = 16×155, 3312 = 16×207, 긴 변 3312, 2480×3312 = 8,213,760 픽셀.
#     2560x1440 을 넘는 해상도는 OpenAI 가 아직 실험적이라고 적어 두었다 —
#     결과가 이상하면 가장 먼저 의심할 값이다.
SIZE = "2480x3312"
# low·medium·high·auto 는 공통, xhigh·max 는 2.5 계열만 받는다. 지금은 high.
QUALITY = "high"
# ── 내보내는 형식 ──────────────────────────────────────────
#   ★ PNG 이 아니다. 화면까지 오는 길에 한도가 하나 있다 —
#     결과는 data URL(base64)로 JSON 에 실려 Vercel 함수(api/v1/virtual-fitting.js)를
#     거쳐 온다. Vercel 함수의 응답 본문 상한은 4.5MB 인데, 2480x3312 PNG 은
#     10MB 안팎이고 base64 로 싸면 1.33배라 13MB 쯤 된다 — 그대로 두면 배포된
#     화면에서는 4K 가 한 장도 안 나온다. webp 는 같은 해상도를 1~2MB 로 담는다.
#     quality(생성 품질)와는 별개다 — 그림을 덜 그리는 게 아니라 담는 그릇만 바꾼다.
#   되돌리려면 이 두 줄만 "png" 로 바꾸면 된다(대신 위의 한도를 먼저 풀어야 한다).
OUTPUT_FORMAT = "webp"
#   ★ 85 는 너무 낮았다 (2026-09-14). 원단 결과 머리카락이 눈에 띄게 뭉개져서
#     "4K 로 올렸는데 오히려 화질이 나빠졌다" 는 말을 들었다. 100 으로 올려도
#     같은 사진이 1MB 안쪽이라(base64 1.4MB) 4.5MB 한도에 한참 못 미친다 —
#     아낄 이유가 없던 자리에서 화질을 깎고 있었다.
OUTPUT_COMPRESSION = "100"
MIME = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}
# 칸 수만큼은 받을 수 있어야 한다 — 칸을 9개로 늘려 놓고 6장에서 자르면
# 사용자가 채운 사진이 조용히 버려진다.
# ★ 다만 API 한 번에 16장이고 기준 사진이 7장을 먼저 쓴다. 칸을 더 늘리려면
#   기준 사진을 줄이든지 해야 한다 — 조용히 잘리지 않게 여기서 함께 계산한다.
MAX_ITEMS = min(len(SLOT_ORDER), MAX_IMAGES - REFERENCE_COUNT)

# 칸마다 어떻게 입혀야 하는가. prompt() 가 이 표를 읽는다 —
# 칸을 늘릴 때 프롬프트 문장을 손으로 이어 붙이지 않도록 한자리에 모은다.
WEAR_GUIDE = {
    # ★ '여밈 방식' 이다 — 단추·지퍼가 어디에 어떻게 달렸나. 열었나 여몄나(상태)는
    #   옵션(top_open/top_closed)이 정한다. 예전 "여밈 … 그대로" 는 기본 '열어 입기'
    #   문장과 맞섰다 (2026-10-01).
    "상의": "상체에 입히고 기장과 여밈 방식(단추·지퍼 위치)은 상품 사진을 그대로 따르세요",
    "하의": "허리선에 맞춰 입히고 기장과 밑단 처리를 그대로 두세요",
    "아우터": "상의 위에 겹쳐 입히고 어깨선과 소매 길이를 몸에 맞추세요",
    "원피스(셋업)": "한 벌로 입히고 다른 상·하의와 겹치지 않게 하세요",
    "신발": "두 발에 맞춰 신기고 발목 각도와 바닥 접지를 자연스럽게 하세요",
    "양말": "신발 안쪽과 발목 높이에 맞게 자연스럽게 신기세요",
    "모자": "머리 크기에 맞춰 씌우고 헤어라인과 머리 모양이 부자연스럽게 눌리지 않게 하세요",
    "벨트": "허리선의 벨트 고리 위치에 채우고 버클 방향과 남는 스트랩을 자연스럽게 두세요",
    "안경": "눈 위치와 얼굴 폭에 맞춰 씌우고 렌즈 너머로 눈이 비치게 하세요",
}

# ── 착장 옵션 (2026-09-14) ──────────────────────────────────
#   ★ 켠 것만 문장이 붙는다. 전부 꺼 두면 예전 프롬프트와 같다 —
#     끄는 것이 "닫아라"는 지시가 되면 사용자가 고르지 않은 연출이 들어간다.
#   ★ 2026-10-01 — 화면이 바뀌었다. 열기/여미기는 칸(상의·아우터)마다 스위치 하나이고
#     기본이 '열어 입기' 다. 그래서 이제 **아무 것도 안 만진 요청에도 outer_open ·
#     top_open 이 실린다.** 두 가지를 같이 고쳤다.
#       ① 문장이 그 칸의 옷이 있을 때만 붙는다(SLOT_OF). 하의만 넣었는데 "아우터는 앞을
#          열어" 가 실리면 모델이 없던 아우터를 그려 넣는다.
#       ② 여밈이 없는 옷(티셔츠·니트·풀오버)은 그대로 두라고 문장 안에서 말한다. 기본이
#          켜진 이상, 이 옷에 열린 트임을 새로 만들라는 지시가 되면 안 된다.
#     상의를 '열어 입기' 로 두고 안에 받쳐 입을 것이 없을 때는 맨살이 드러나지 않게
#     단추를 위쪽만 풀라고 적는다 — 기본값이 사진을 망치면 안 된다.
OPTION_LINES = {
    "outer_layered": ("아우터가 둘 이상이면 얇고 짧은 것을 안쪽, 두껍고 긴 것을 "
                      "바깥쪽으로 두어 자연스럽게 레이어드하세요."),
    # ★ 2026-10-02 — 문장마다 "그 칸의 상품이 있을 때만" 을 못 박는다. 상의만 넣고
    #   기본 '열어 입기' 로 보냈더니, 모델이 '열어 입은 모습' 을 만들려고 없던 아우터를
    #   그려 넣었다. 칸을 모르는 사진('자동 분류')이 섞이면 이 문장이 그대로 실리기 때문에
    #   (option_keys), 문장 스스로도 조건을 말해야 한다.
    "outer_open": ("아우터 상품이 있을 때만 해당합니다 — 앞여밈(지퍼·단추)이 있는 아우터는 앞을 "
                   "열어 입은 상태로 표현하고 안에 입은 옷이 보이게 하세요. 앞여밈이 없는 아우터는 "
                   "그대로 두세요. 아우터 상품이 없으면 이 지시는 무시하고 아우터를 새로 만들지 마세요."),
    "outer_closed": ("아우터 상품이 있을 때만 해당합니다 — 앞여밈(지퍼·단추)이 있는 아우터는 앞을 "
                     "여미거나 잠근 상태로 표현하세요. 아우터 상품이 없으면 아우터를 새로 만들지 마세요."),
    "top_open": ("앞여밈(단추·지퍼)이 있는 상의는 앞을 열어 입은 상태로 표현하세요. 안에 받쳐 "
                 "입은 상의가 없으면 단추를 위쪽 한두 개만 풀어 자연스럽게 연출하세요. "
                 "티셔츠·니트처럼 앞여밈이 없는 상의는 그대로 두고 트임을 새로 만들지 마세요. "
                 "열어 입은 모습을 만들려고 겉옷이나 이너를 새로 더하지 마세요."),
    "top_closed": "앞여밈(단추·지퍼)이 있는 상의는 끝까지 여민 상태로 표현하세요.",
    # ── 핏 (2026-10-01) — 화면은 오버핏 · 정핏 · 슬림핏 세 칸, 기본 정핏.
    #   정핏은 문장을 붙이지 않는다 — 상품 사진의 핏 그대로가 정핏이고, 예전 동작이다.
    "fit_over": ("핏은 오버핏으로 표현하세요 — 한두 치수 크게 입은 것처럼 어깨선이 살짝 "
                 "내려오고 몸판·소매·바짓단에 여유가 생기게 하세요. 이 핏 지시가 상품 "
                 "사진의 실루엣보다 우선합니다."),
    "fit_slim": ("핏은 슬림핏으로 표현하세요 — 몸판·소매·바짓단이 몸선을 따라 좁게 "
                 "떨어지게 하세요. 이 핏 지시가 상품 사진의 실루엣보다 우선합니다."),
}
# 서로 맞서는 짝. 둘 다 켜져 오면 어느 쪽도 쓰지 않는다 —
# 모순된 지시를 보내느니 모델이 알아서 하게 두는 편이 낫다.
OPTION_CONFLICTS = [("outer_open", "outer_closed"), ("top_open", "top_closed"),
                    ("fit_over", "fit_slim")]
# 이 옵션은 이 칸의 옷이 있을 때만 의미가 있다. 칸을 모르는 사진('자동 분류')이
# 있으면 그 사진이 이 칸일 수 있으니 붙인다 — 문장 자체가 조건부다.
SLOT_OF = {"outer_open": "아우터", "outer_closed": "아우터",
           "top_open": "상의", "top_closed": "상의"}
FIT_KEYS = ("fit_over", "fit_slim")


def option_keys(options, categories: list[str] | None = None) -> list[str]:
    """프롬프트에 실제로 실을 옵션 이름. 모르는 이름은 조용히 버린다.

    categories 를 주면 그 칸의 옷이 없는 옵션을 뺀다(None 이면 칸을 보지 않는다).
    """
    if not isinstance(options, dict):
        return []
    on = [k for k in OPTION_LINES if options.get(k)]
    for a, b in OPTION_CONFLICTS:
        if a in on and b in on:
            on = [k for k in on if k not in (a, b)]
    if categories is not None:
        cats = set(categories)
        on = [k for k in on
              if k not in SLOT_OF or SLOT_OF[k] in cats or AUTO in cats]
    return on


def option_lines(options, categories: list[str] | None = None) -> list[str]:
    """켜진 옵션만 문장으로."""
    return [OPTION_LINES[k] for k in option_keys(options, categories)]


# ── 생성 직전에 사진을 본다 (2026-10-02) ─────────────────────
#   왜 —
#     화면에서 직접 올린 사진은 'Auto(자동 분류)' 로 온다. option_keys 는 칸을 모르는
#     사진이 있으면 "그 사진이 아우터일 수도 있다" 며 아우터 열기 문장을 붙인다. 그
#     결과 상의(티셔츠)만 넣고 기본 '열어 입기' 로 보냈는데 없던 아우터가 그려졌다.
#     챗봇 코디(build_fit)는 이미 사진을 보고(fit.prune_options) 연출을 고르지만,
#     화면에서 바로 오는 요청은 그 길을 거치지 않았다.
#   무엇을 —
#     상품 사진을 vision 에 한 번 묻는다(inspect · 오후부터는 전부 — sight_targets 주석).
#     칸을 모르던 사진은 본 칸으로 정하고, 여밈이 없다고 확인된 옷뿐이면 그 칸의
#     열기/여미기를 빼고, 사람이 입고 찍힌 사진은 프롬프트가 번호를 집어 옷만 가져오게 한다.
#   ★ 사용자가 고른 칸은 바꾸지 않는다 — 고른 사람이 맞다.
#   ★ 모르면 빼지도 바꾸지도 않는다(AGENTS.md §6). 사진을 못 보면 예전 그대로 가고,
#     문장 자체의 조건(NO_INVENT · '아우터 상품이 있을 때만')이 남아서 막는다.
OPEN_KEYS = {"상의": ("top_open", "top_closed"), "아우터": ("outer_open", "outer_closed")}


def sight_targets(categories: list[str], options) -> list[int]:
    """생성 전에 볼 상품 사진의 번호(0부터) — 전부다.

    ★ 2026-10-02 (오후) — 예전에는 연출(열기/여미기 · 레이어드)이 걸린 사진만 봤다.
      그런데 상품 사진에 **다른 사람이 입고 찍힌 사진**(착용 컷 · 인스타 · 연예인 코디)이
      들어오면, 생성 모델이 그 사진의 장면을 바탕으로 삼아 우리 모델을 통째로 버렸다
      (셔츠 착용 사진의 남자에게 바지 · 신발만 갈아 신긴 결과). 어느 사진이 착용 컷인지
      알아야 프롬프트가 그 사진을 콕 집어 "옷만 가져오라" 고 말할 수 있다. 사진은 한
      번의 호출로 같이 본다 — 생성(수십 초) 앞에 붙는 몇 초다(sight_ms 로 잰다).
    """
    return list(range(len(categories)))


def apply_sight(categories: list[str], options, seen: dict[int, dict]
                ) -> tuple[list[str], dict, list[str]]:
    """본 결과(seen: 번호 → inspect 한 줄)로 칸과 연출을 정한다.

    돌려주는 것: (프롬프트에 쓸 칸, 실을 옵션 {이름: True}, 무엇을 왜 바꿨나)
    """
    cats = list(categories)
    notes: list[str] = []
    for i, look in seen.items():
        slot = (look or {}).get("slot")
        if cats[i] == AUTO and slot in SLOT_ORDER:
            cats[i] = slot
            notes.append(f"{i + 1}번 상품은 사진상 {slot} 로 보고 입혔습니다.")
    on = option_keys(options, cats)
    for slot, keys in OPEN_KEYS.items():
        if not any(k in on for k in keys):
            continue
        looks = [seen.get(i) or {} for i, c in enumerate(cats) if c == slot]
        # 그 칸의 옷이 모두 '여밈 없음' 으로 확인됐을 때만 뺀다. 하나라도 모르면 둔다.
        if looks and all(look.get("openable") == "no" for look in looks):
            on = [k for k in on if k not in keys]
            notes.append(f"{slot}에 앞여밈이 없어 {slot} 열기/여미기는 빼고 입혔습니다.")
    if "outer_layered" in on and AUTO not in cats and cats.count("아우터") < 2:
        on = [k for k in on if k != "outer_layered"]
        notes.append("아우터가 한 벌이라 레이어드는 빼고 입혔습니다.")
    return cats, {k: True for k in on}, notes


_DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,(.+)$", re.I | re.S)


def decode_image(data_url: str, max_bytes: int = 5 * 1024 * 1024) -> tuple[bytes, str]:
    hit = _DATA_URL.match(str(data_url or ""))
    if not hit:
        raise ValueError("지원하는 이미지 형식이 아닙니다.")
    try:
        raw = base64.b64decode(hit.group(2), validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("이미지를 읽을 수 없습니다.") from exc
    if not raw or len(raw) > max_bytes:
        raise ValueError("이미지는 5MB 이하만 사용할 수 있습니다.")
    ext = "jpg" if hit.group(1).lower() == "image/jpeg" else hit.group(1).split("/")[1]
    return raw, ext


# ── DB 상품 사진을 주소로 받는다 (2026-09-22) ────────────────
#   왜 서버가 받나 —
#     상품 썸네일(commerce.product_source.thumbnail_url)은 플랫폼 CDN 주소다.
#     화면에서 fetch 하면 CORS 로 막히고, 막히는 자리가 브라우저라 서버 로그에는
#     아무것도 안 남는다. 받는 쪽을 서버로 옮긴다.
#   부수 이득 — 요청 본문이 몇 백 바이트로 줄어 버셀 중계 함수의 4.5MB 상한
#     (api/v1/virtual-fitting.js)에 걸리지 않는다.
#   ★ 아무 주소나 대신 받아 주지 않는다. 허용한 호스트만 — 그러지 않으면 우리
#     서버가 남의 요청을 대신 쏘는 통로(SSRF)가 된다.
#   ★ 호스트 목록은 환경변수로 넓힌다. 실제 값은 DB 가 원본이다:
#       SELECT DISTINCT split_part(thumbnail_url,'/',3) FROM commerce.product_source;
#   ★ 아래 넷은 2026-09-22 DB 실측이다(commerce.product_source 72,352건):
#       image.msscdn.net 24,251 · cf.product-image.s3.zigzag.kr 18,268 ·
#       d3ha2047wt6x28.cloudfront.net 1,353 · kream-phinf.pstatic.net 655.
#     같은 조회에서 호스트가 아예 없는 상대 경로가 27,424건 나왔다 — 그것은
#     fit.absolute_image() 가 주소로 만든다.
#   ★ 2026-10-01 — 지그재그 사진이 **s3 가 없는** 호스트(cf.product-image.s.zigzag.kr)로도
#     온다. 운영 /api/products 실측: 긱시크·미니멀 상의·하의 21건 중 7건이 이 호스트였고,
#     목록에 없어 코디에서 전부 빠졌다. 둘 다 받는다.
ALLOWED_IMAGE_HOSTS = {
    h.strip().lower() for h in (
        os.getenv("FEEDIT_VTON_IMAGE_HOSTS")
        or "image.msscdn.net,cf.product-image.s3.zigzag.kr,cf.product-image.s.zigzag.kr,"
           "d3ha2047wt6x28.cloudfront.net,kream-phinf.pstatic.net"
    ).split(",") if h.strip()
}
FETCH_TIMEOUT = 8
FETCH_MAX_BYTES = 5 * 1024 * 1024


def image_host_allowed(url: str) -> bool:
    """이 주소를 우리가 받아도 되는가. 사진을 보내기 전에 먼저 묻는 자리다."""
    return (urlparse(str(url or "")).hostname or "").lower() in ALLOWED_IMAGE_HOSTS


def fetch_as_data_url(url: str, max_bytes: int = FETCH_MAX_BYTES) -> str:
    """상품 사진 주소 하나를 data URL 로 바꾼다. 실패는 사유를 담아 올린다."""
    host = (urlparse(str(url or "")).hostname or "").lower()
    if not host:
        raise ValueError("상품 사진 주소를 읽을 수 없습니다.")
    if host not in ALLOWED_IMAGE_HOSTS:
        # ★ 호스트를 문구에 적는다 — 목록에 한 줄 더하면 되는 일을, 화면만 보고는
        #   무엇이 막혔는지 알 수 없던 자리다.
        raise ValueError(f"허용되지 않은 상품 사진 주소입니다 ({host}) — "
                         f"FEEDIT_VTON_IMAGE_HOSTS 를 확인하세요.")
    try:
        # 일부 CDN 은 User-Agent 없는 요청을 막는다.
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                           timeout=FETCH_TIMEOUT)
        res.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"상품 사진을 받지 못했습니다 ({type(exc).__name__}).") from exc
    mime = (res.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if mime not in set(MIME.values()):
        raise ValueError(f"지원하는 이미지 형식이 아닙니다 ({mime or '알 수 없음'}).")
    raw = res.content
    if not raw or len(raw) > max_bytes:
        raise ValueError("상품 사진은 5MB 이하만 사용할 수 있습니다.")
    return "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")


# ★ 주지 않은 옷을 지어내지 않는다 (2026-10-02). 옵션과 상관없이 늘 싣는다 —
#   상품이 없는 부위는 포즈 사진의 옷이 기준이다. 이 문장이 없을 때 '열어 입기' 같은
#   연출 지시를 맞추려고 모델이 아우터 · 가디건을 새로 그려 넣었다.
# ── 상품 사진 속 사람 (2026-10-02 오후) ───────────────────────
#   상의 칸에 '남자가 흰 셔츠를 입고 의자에 앉은 사진' 을 넣고 여성 모델로 만들었더니,
#   결과가 그 사진 그대로였다 — 같은 남자 · 같은 배경에 바지와 신발만 바뀌었다. 우리
#   모델 사진 일곱 장과 프롬프트가 통째로 무시된 것처럼 보였다.
#   원인: 상품 사진도 '사람이 찍힌 완성된 장면' 이면 생성 모델이 그것을 고칠 바탕으로
#   고를 수 있다. 프롬프트는 상품 사진에 사람이 있을 수 있다는 말을 한 번도 하지 않았다.
#   ★ 인스타 · 연예인 코디를 입혀 보는 흐름은 거의 언제나 착용 컷이다 — 예외가 아니다.
ITEM_ONLY = (f"{REFERENCE_COUNT + 1}번째 이미지부터의 상품 사진은 옷 견본일 뿐입니다. 상품 사진에 "
             "사람이 입고 있어도 그 사람은 다른 사람입니다 — 그 사진의 얼굴, 머리, 체형, 자세, "
             "배경, 조명, 구도는 하나도 쓰지 말고, 칸으로 지정한 옷만 떼어 오세요. 그 사람이 함께 "
             "입은 다른 옷도 가져오지 마세요. 결과 사진의 인물은 반드시 1~6번의 사람이고, 자세와 "
             f"배경과 구도는 {REFERENCE_COUNT}번 사진입니다. 상품 사진의 장면을 결과의 바탕으로 "
             "쓰면 안 됩니다.")
NO_INVENT = (f"입힐 상품으로 준 옷과 잡화만 더하세요. 상품으로 주지 않은 종류(아우터·가디건·"
             f"조끼·모자·가방·액세서리 등)를 새로 만들어 넣지 마세요 — 상품이 없는 부위는 "
             f"{REFERENCE_COUNT}번 사진에서 입고 있는 옷을 그대로 두세요.")


# ── 착용 컷에서 사람을 걷어 낸다 (2026-10-02 오후 2차) ───────
#   프롬프트로 "상품 사진 속 사람은 다른 사람" 을 못 박은 뒤에도, 여성 모델로 만든 결과에
#   상품 사진의 남자가 그대로 나왔다(정장 착용 컷 · Flare). 말로는 부족했다 — 다른 사람의
#   얼굴과 몸이 들어 있는 장면을 보내는 한, 생성 모델은 그 장면을 고를 수 있다.
#   그래서 보내기 전에 착용 컷을 그 칸 옷 영역(box)으로 잘라 내고, 머리(head)는 덮는다.
#   ★ 상자를 못 받았거나 Pillow 가 없으면 원본을 그대로 보낸다 — 옷을 잃는 것보다 낫고,
#     프롬프트(ITEM_ONLY · 결과 인물의 성별)가 남아서 막는다.
ISOLATE_PAD = 0.06          # 옷이 잘리지 않게 상자 밖으로 이만큼 더 둔다(사진 폭·높이 비율)
HEAD_PAD = 0.12             # 머리 상자는 더 넉넉히 덮는다 — 턱선·머리카락이 남지 않게
COVER = (241, 239, 234)     # 덮는 색 — FEEDiT 페이퍼. 검정은 옷(검은 재킷)과 섞인다.


def isolate(raw: bytes, ext: str, look: dict | None) -> tuple[bytes, str, bool]:
    """착용 컷이면 옷 영역만 남기고 머리를 덮은 사진을 돌려준다. (바이트, 확장자, 바꿨나)"""
    look = look or {}
    box, head = look.get("box") or [], look.get("head") or []
    if look.get("worn") != "yes" or not (box or head):
        return raw, ext, False
    try:
        import io
        from PIL import Image, ImageDraw
    except ImportError:
        return raw, ext, False
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = img.convert("RGB")
        w, h = img.size

        def px(b, pad):
            return (max(0, int((b[0] - pad) * w)), max(0, int((b[1] - pad) * h)),
                    min(w, int((b[2] + pad) * w)), min(h, int((b[3] + pad) * h)))

        if head:
            ImageDraw.Draw(img).rectangle(px(head, HEAD_PAD), fill=COVER)
        if box:
            img = img.crop(px(box, ISOLATE_PAD))
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue(), "png", True
    except Exception:  # noqa: BLE001 — 자르기는 거드는 일이다. 실패하면 원본.
        return raw, ext, False


# ── 결과 사진 위 쇼핑 태그 (2026-10-02) ─────────────────────
#   결과를 보고 마음에 든 순간 "이 재킷 어디 거야?" 에 답하려면, 사진 위 옷 자리에 점을
#   찍어야 한다. 포즈가 매번 달라 칸마다 정해 둔 자리로는 맞지 않는다 — 만든 사진을
#   vision 이 한 번 보고 상품마다 한 점을 준다.
#   ★ 큰 결과(2480x3312)를 그대로 보내지 않는다. 긴 변 1024 로 줄여 보낸다(Pillow 가
#     없으면 원본). 점 하나 찍는 데 4K 는 필요 없고, 기다림만 길어진다.
#   ★ 안 보이는 상품은 점을 찍지 않는다(빈 배열). 모르면 지어내지 않는다.
LOCATE_SIDE = 1024
_LOCATE_INSTRUCTIONS = (
    "FEEDiT 착용 사진의 쇼핑 태그를 찍습니다. 사진 속 인물이 입은 상품마다, 그 상품 위의 "
    "한 점을 고르세요 — 그 옷의 가운데쯤, 다른 옷과 겹치지 않고 그 상품이 분명히 보이는 "
    "자리입니다. 사진 폭·높이를 1로 본 [x, y] 비율입니다(왼쪽 위가 0, 0).\n"
    "상품이 사진에서 보이지 않거나 어디인지 확실하지 않으면 빈 배열을 주세요. "
    "지어내지 마세요.\n"
    "items 배열은 주어진 상품과 같은 순서, 같은 개수로 돌려주세요."
)


def _locate_schema():
    from . import llm
    row = {"type": "object", "additionalProperties": False,
           "properties": {"point": {"type": "array", "items": {"type": "number"}}},
           "required": ["point"]}
    return llm.strict_schema("feedit_vton_tags",
                             {"items": {"type": "array", "items": row}}, ["items"])


def _small_data_url(encoded: str) -> str:
    """결과(base64)를 긴 변 LOCATE_SIDE 의 JPEG data URL 로. 못 줄이면 원본 그대로."""
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(base64.b64decode(encoded)))
        img.load()
        img = img.convert("RGB")
        img.thumbnail((LOCATE_SIDE, LOCATE_SIDE))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()
    except Exception:  # noqa: BLE001 — Pillow 가 없거나 못 읽으면 원본을 보낸다
        return "data:" + MIME.get(OUTPUT_FORMAT, "image/png") + ";base64," + encoded


def locate(encoded: str, items: list[tuple[str, str]]) -> list[dict]:
    """결과 사진에서 상품마다 한 점. [{"index", "x", "y"}] — 못 찾은 상품은 빠진다."""
    from . import llm

    if not encoded or not items or not llm.available():
        return []
    listing = "\n".join(f"{i + 1}. {cat}" + (f" — {name}" if name else "")
                         for i, (cat, name) in enumerate(items))
    content = [{"type": "input_text", "text": "상품 목록:\n" + listing},
               {"type": "input_image", "image_url": _small_data_url(encoded)}]
    try:
        got = llm.respond(_LOCATE_INSTRUCTIONS, [{"role": "user", "content": content}],
                          _locate_schema(), timeout=20, **llm.role("vision"))
    except Exception:  # noqa: BLE001 — 태그는 거드는 일이다. 실패하면 태그 없이 간다.
        return []
    rows = (got or {}).get("items")
    if not isinstance(rows, list):
        return []
    out = []
    for i, row in enumerate(rows[:len(items)]):
        point = (row or {}).get("point") if isinstance(row, dict) else None
        try:
            x, y = (float(v) for v in point)
        except (TypeError, ValueError):
            continue
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            out.append({"index": i, "x": round(x, 4), "y": round(y, 4)})
    return out


def prompt(categories: list[str], options: dict | None = None,
           worn: list[bool] | None = None, who: str | None = None,
           cut: list[bool] | None = None) -> str:
    """보내는 이미지 순서를 그대로 글로 옮긴다.

    ★ 번호가 references() 의 순서와 한 칸도 어긋나면 안 된다 —
        1~3   얼굴 기준 (정면 · 우45 · 좌45)
        4~6   체형 기준 (전신 정면 · 측면 · 후면)
        7     이번 컷의 자세와 구도
        8~    입힐 상품
      기준 사진을 늘리거나 줄이면 MASTER_COUNT 와 이 문장을 같이 고쳐야 한다.
    worn 은 상품마다 '사람이 입고 찍힌 사진인가' (inspect 의 worn == "yes"). 그런 사진은
    번호를 집어 옷만 가져오라고 한 번 더 말한다.
    cut 은 상품마다 '착용 컷에서 옷 부분만 잘라 보냈나' (isolate). 잘랐을 때만 그렇다고 말한다.
    who 는 고른 모델의 성별 단어('여성' · '남성'). 주면 결과 인물의 성별을 처음과 끝에서
    못 박는다 — 상품 사진에 다른 성별의 사람이 있어도 결과는 고른 모델이다.
    """
    cats = [c if c in CATEGORIES else AUTO for c in categories]
    first = REFERENCE_COUNT + 1                 # 상품이 시작하는 번호
    worn, cut = list(worn or []), list(cut or [])

    def guide(i: int, category: str) -> str:
        head = f"{i + first}번째 이미지는 " + ("사진을 보고 종류를 먼저 판별" if category == AUTO
                                              else category)
        what = "그 옷" if category == AUTO else category
        if i < len(cut) and cut[i]:
            head += (f"(다른 사람이 입고 찍힌 사진에서 {what} 부분만 잘라 낸 것입니다 — "
                     f"{what}만 가져오고 사진 속 몸의 모양·성별·자세와 배경은 쓰지 마세요)")
        elif i < len(worn) and worn[i]:
            head += (f"(다른 사람이 입고 찍힌 사진입니다 — {what}만 가져오고 그 사람의 "
                     "몸·성별·자세와 배경은 쓰지 마세요)")
        return head if category == AUTO else f"{head} — {WEAR_GUIDE[category]}"

    item_guide = ", ".join(guide(i, category) for i, category in enumerate(cats))
    body = []
    if who:
        body.append(f"결과 사진의 인물은 반드시 1~6번 기준 사진의 {who} 한 사람입니다. 상품 "
                    f"사진에 다른 사람(다른 성별 포함)이 있어도 결과 인물은 이 {who}입니다.")
    body += [
        f"1번부터 {REFERENCE_COUNT}번까지는 모두 같은 한 사람을 찍은 기준 사진입니다. "
        "새로운 인물을 만들지 말고 이 사람을 그대로 쓰세요.",
        "1~3번은 얼굴 기준(정면·우45·좌45)입니다. 이목구비, 얼굴형, 피부 톤, "
        "머리 색과 길이와 결을 이 셋과 같게 하세요.",
        "4~6번은 체형 기준(전신 정면·측면·후면)입니다. 키, 어깨너비, 허리와 골반 "
        "폭, 팔다리 길이와 굵기를 이 셋과 같게 하세요.",
        # ★ 다리가 짧아 보인다는 말을 자주 들었다 (2026-09-14). 자세를 따라
        #   그리다 보면 허리선과 다리 길이가 같이 눌린다 — 비율만은 체형 기준을
        #   보라고 따로 못 박는다. 포즈 쪽에서도 단축법이 심한 컷은 빼 두었다.
        "특히 다리 길이와 허리선 높이는 4~6번의 비율을 그대로 지키세요. "
        "자세 때문에 다리가 짧아 보이게 만들지 마세요.",
        f"{REFERENCE_COUNT}번은 이번 컷의 기준입니다. 자세, 팔다리 위치, 얼굴 방향, "
        "카메라 각도, 화면 안에서의 크기와 위치, 배경과 조명을 이 사진 그대로 두세요.",
        f"{first}번째 이미지부터가 입힐 상품입니다. {item_guide}.",
        ITEM_ONLY,
        # ★ 핏을 골랐으면 '실루엣 보존' 을 빼고 말한다 — 같은 프롬프트 안에서 "실루엣을
        #   그대로" 와 "오버핏으로" 가 맞서면 모델이 어느 쪽도 제대로 하지 않는다.
        ("각 상품의 색상, 패턴, 로고, 소재 질감, 봉제선을 정확히 보존하세요."
         if any(k in FIT_KEYS for k in option_keys(options, cats))
         else "각 상품의 색상, 패턴, 로고, 소재 질감, 봉제선과 실루엣을 정확히 보존하세요."),
        "여러 상품은 실제 옷을 입는 순서와 레이어 관계에 맞춰 하나의 코디로 조합하세요.",
        NO_INVENT,
    ]
    body += option_lines(options, cats)
    body += [
        f"바꾸는 것은 옷뿐입니다. 얼굴, 머리, 체형, 자세, 배경, 조명은 "
        f"기준 사진 그대로 두세요 — 특히 얼굴이 다른 사람처럼 보이면 안 되고, "
        f"상품 사진 속 인물이나 배경이 결과에 나오면 안 됩니다.",
        f"사진처럼 자연스러운 전신 패션 화보로 만들고 {REFERENCE_COUNT}번 이미지와 "
        "같은 구도를 유지하세요.",
    ]
    if who:
        body.append(f"다시 확인하세요 — 결과 인물은 1~6번의 {who}이고, 자세와 배경은 "
                    f"{REFERENCE_COUNT}번입니다. 상품 사진의 사람이나 장면이 나오면 실패입니다.")
    return " ".join(body)


def _items(items: list[dict] | None, image_data_url: str | None,
           category: str | None) -> list[dict]:
    """새 다중 입력과 이전 단일 입력을 같은 검증 경로로 정리한다."""
    rows = items if isinstance(items, list) else []
    if not rows and image_data_url:
        rows = [{"image": image_data_url, "category": category or "상의"}]
    clean = []
    for row in rows[:MAX_ITEMS]:
        if not isinstance(row, dict):
            continue
        # ★ 사진은 data URL 이거나 상품 사진 주소다 (2026-09-22). 주소로 오면
        #   여기서 받아 둔다 — 아래 decode_image 는 data URL 만 읽는다.
        if not row.get("image") and row.get("image_url"):
            row = {**row, "image": fetch_as_data_url(str(row["image_url"]))}
        if not row.get("image"):
            continue
        cat = str(row.get("category") or AUTO)
        clean.append({"image": str(row["image"]),
                      "category": cat if cat in CATEGORIES else AUTO,
                      # 상품 이름 — 결과 사진에서 옷 자리를 찾을 때(locate) 무엇을 찾는지 알려 준다.
                      "name": str(row.get("name") or "").strip()[:80]})
    if not clean:
        raise ValueError("입혀볼 아이템 사진이 필요합니다.")
    return clean


def generate(*, model_id: str, items: list[dict] | None = None,
             image_data_url: str | None = None, category: str | None = None,
             options: dict | None = None, pose: str | None = None,
             engine: str | None = None, tags: bool = False) -> dict:
    model = MODELS.get(model_id)
    engine = engine_of(engine)
    image_model = ENGINES[engine]["model"]
    if not model:
        raise ValueError(f"'{model_id}' 는 없는 AI 모델입니다 "
                         f"(쓸 수 있는 것: {', '.join(sorted(MODELS))}).")
    # 마스터 여섯 장 + 이번 컷의 포즈 한 장. 마지막 것이 뽑힌 포즈다.
    refs = references(model_id, pose)
    model_path = refs[-1]
    chosen = _items(items, image_data_url, category)
    decoded = [(decode_image(row["image"]), row["category"]) for row in chosen]
    if sum(len(raw) for ((raw, _ext), _cat) in decoded) > 20 * 1024 * 1024:
        raise ValueError("아이템 이미지 전체 용량은 20MB 이하만 사용할 수 있습니다.")
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    categories = [row["category"] for row in chosen]
    # 연출을 정하려면 사진을 봐야 하는 상품만 vision 에 묻는다(sight_targets).
    # 걸린 시간은 따로 남긴다 — 생성 시간을 줄이는 중이라 이 몫이 얼마인지 알아야 한다.
    sight_started = time.monotonic()
    targets = sight_targets(categories, options)
    try:
        seen = dict(zip(targets, inspect([chosen[i]["image"] for i in targets],
                                         [categories[i] for i in targets]))) if targets else {}
    except Exception:  # noqa: BLE001 — 검수는 거드는 일이다. 실패해도 생성은 간다(예전 그대로).
        seen = {}
    sight_ms = int((time.monotonic() - sight_started) * 1000) if targets else 0
    categories, options, sight_notes = apply_sight(categories, options, seen)
    worn = [(seen.get(i) or {}).get("worn") == "yes" for i in range(len(chosen))]
    if any(worn):
        sight_notes.append(", ".join(f"{i + 1}번" for i, w in enumerate(worn) if w) +
                           " 상품은 사람이 입고 찍힌 사진이라 옷만 가져오게 했습니다.")
    # 착용 컷은 옷 영역만 남기고 머리를 덮어 보낸다(isolate).
    isolated = []
    for i, ((raw, ext), cat) in enumerate(decoded):
        raw, ext, changed = isolate(raw, ext, seen.get(i))
        decoded[i] = ((raw, ext), cat)
        if changed:
            isolated.append(i + 1)
    if isolated:
        sight_notes.append(", ".join(f"{n}번" for n in isolated) +
                           " 상품은 옷 부분만 잘라 내고 얼굴을 가려 보냈습니다.")
    started = time.monotonic()
    # ★ 기준 사진이 먼저, 상품이 나중 — prompt() 가 부르는 번호 그대로다.
    #   파일은 보내는 동안 열어 둔다(ExitStack). 하나씩 열고 닫으면 requests 가
    #   읽을 때는 이미 닫혀 있다.
    with contextlib.ExitStack() as stack:
        files = [("image[]", (path.name, stack.enter_context(path.open("rb")),
                              "image/png"))
                 for path in refs]
        for index, ((raw, ext), _cat) in enumerate(decoded, start=1):
            files.append(("image[]",
                          (f"item-{index}.{ext}", raw,
                           f"image/{'jpeg' if ext == 'jpg' else ext}")))
        response = requests.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {key}"},
            data={"model": image_model,
                  "prompt": prompt(categories, options, worn, model.get("who"),
                                   [i + 1 in isolated for i in range(len(chosen))]),
                  "size": SIZE, "quality": QUALITY,
                  "output_format": OUTPUT_FORMAT,
                  "output_compression": OUTPUT_COMPRESSION,
                  "n": "1"},
            files=files,
            # 4K·high 한 장은 1024 정사각보다 한참 오래 걸린다.
            # 120초로는 다 만들어 놓고도 우리가 먼저 끊는다.
            timeout=300,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"이미지 생성 요청이 실패했습니다 (HTTP {response.status_code}).")
    payload = response.json()
    encoded = ((payload.get("data") or [{}])[0]).get("b64_json")
    if not encoded:
        raise RuntimeError("생성된 이미지를 받지 못했습니다.")
    mime = MIME.get(OUTPUT_FORMAT, "image/png")
    elapsed_ms = int((time.monotonic() - started) * 1000)
    # 결과 사진 위 쇼핑 태그 — 화면이 원할 때만(판매처가 있는 상품이 있을 때) 찾는다.
    tag_started = time.monotonic()
    found = locate(encoded, [(c, row["name"]) for c, row in zip(categories, chosen)]) if tags else []
    tag_ms = int((time.monotonic() - tag_started) * 1000) if tags else 0
    return {"image": "data:" + mime + ";base64," + encoded, "model": image_model,
            "engine": engine, "engine_label": ENGINES[engine]["label"],
            # 요청을 보내고 받기까지 — 엔진별로 얼마나 걸리는지 재는 자리다.
            "elapsed_ms": elapsed_ms,
            # 결과 사진에서 상품이 보이는 자리(0~1 비율). index 는 보낸 상품 순서(0부터).
            "tags": found, "tag_ms": tag_ms,
            "model_label": model["label"],
            "size": SIZE, "quality": QUALITY, "format": OUTPUT_FORMAT,
            # 어느 포즈가 뽑혔나 — 같은 자세를 한 번 더 내고 싶을 때 이 이름을
            # pose 로 되돌려 주면 된다.
            "pose": model_path.name,
            # 기준 사진이 실제로 몇 장 실렸나 — 폴더가 비어도 조용히 넘어가지
            # 않게 여기서 드러낸다.
            "references": [path.name for path in refs],
            "categories": categories,
            # 어떤 옵션이 실제로 프롬프트에 실렸나. 화면엔 안 뜨지만 로그로 본다.
            "options": option_keys(options, categories),
            # 사진을 보고 바꾼 것 — 칸을 정했거나 연출을 뺀 이유. 화면 · 로그가 읽는다.
            "sight_notes": sight_notes, "sight_ms": sight_ms,
            # 사람이 입고 찍힌 상품 사진의 번호(1부터) — 결과가 그 장면을 닮았는지 볼 때 쓴다.
            "worn": [i + 1 for i, w in enumerate(worn) if w],
            # 옷 영역만 잘라 보낸 상품 번호(1부터)
            "isolated": isolated,
            "item_count": len(chosen)}


# ── 사진 → 착장 칸 자동 분류 (2026-09-13) ──────────────────────
#   왜 서버가 하나 —
#     화면은 사진을 순서대로 칸에 넣을 수밖에 없다. 스커트를 올렸는데 '상의' 칸이
#     차 버리면 사용자가 지우고 다시 넣어야 했다. 어떤 옷인지 아는 것은 사진을
#     볼 수 있는 쪽뿐이라, 판별은 여기서 한다.
#   ★ 값을 지어내지 않는다. 확실하지 않으면 "자동 분류" 로 남긴다 —
#     그러면 생성 프롬프트가 예전처럼 스스로 판별한다(위 prompt()).
SLOTS = list(SLOT_ORDER)

_INSPECT_INSTRUCTIONS = (
    "FEEDiT 착장 합성용 검수기입니다. 각 사진에 담긴 의류·잡화를 보고 네 가지만 "
    "고르세요 — 어느 칸에 들어가는지, 앞을 열 수 있는 옷인지, 겹쳐 입을 때 얇은 "
    "쪽인지, 사람이 입고 찍힌 사진인지.\n"
    "- 상의: 티셔츠·셔츠·니트·블라우스·후디 등 상체에 입는 옷\n"
    "- 하의: 바지·스커트·반바지 등 하체에 입는 옷\n"
    "- 아우터: 코트·재킷·점퍼·가디건 등 겉에 걸치는 옷\n"
    "- 원피스(셋업): 원피스·점프수트·상하 세트\n"
    "- 신발 / 양말: 각각 신발과 양말\n"
    "- 모자: 캡·버킷햇·비니 등 머리에 쓰는 것\n"
    "- 벨트: 허리에 채우는 벨트\n"
    "- 안경: 안경·선글라스\n"
    "- 어느 칸인지 확실하지 않거나 착용물이 아니면 '자동 분류'\n"
    "closure 는 사진에 실제로 보이는 여밈입니다(지퍼·버튼·스냅). 머리로 입는 옷처럼 "
    "여밈이 없으면 '없음', 사진에서 안 보이면 '모르겠음' 입니다.\n"
    "openable 은 앞을 열어 입은 모습으로 그릴 수 있는 옷인지입니다. 여밈이 보이면 "
    "yes, 머리로 입는 옷이면 no, 판단이 안 서면 unknown.\n"
    "layer 는 겹쳐 입을 때의 두께감입니다. 안 보이면 '모르겠음'.\n"
    "worn 은 사람이 실제로 입고(신고·쓰고) 찍힌 사진인지입니다. 착용 컷·거리 사진·셀카처럼 "
    "사람의 몸이나 얼굴이 보이면 yes, 옷만 놓였거나 걸린 사진·마네킹이면 no, 판단이 안 서면 "
    "unknown.\n"
    "★ 지어내지 마세요. 사진에 보이는 것만 보고 고르고, 확실하지 않으면 "
    "'모르겠음'·unknown·'자동 분류' 를 고르세요. 브랜드·가격·트렌드는 판단하지 "
    "마세요.\n"
    "box 는 사람이 입고 찍힌 사진(worn=yes)에서 이 칸 옷이 차지하는 영역입니다. 사진 앞에 "
    "칸이 적혀 있으면 그 칸의 옷 하나만 감싸세요(다른 옷·배경은 되도록 빼고, 옷은 잘리지 "
    "않게). 사진 폭·높이를 1로 본 [왼쪽, 위, 오른쪽, 아래] 비율입니다. worn 이 yes 가 "
    "아니면 빈 배열.\n"
    "head 는 사람이 보이면 그 사람의 머리(얼굴·머리카락) 영역을 같은 비율로, 머리가 안 "
    "보이면 빈 배열입니다.\n"
    "items 배열은 입력한 사진과 같은 순서, 같은 개수로 돌려주세요."
)
# 예전 이름 — /v1/fit-classify 와 테스트가 아직 이 이름을 쓴다.
_CLASSIFY_INSTRUCTIONS = _INSPECT_INSTRUCTIONS
CLOSURES = ["지퍼", "버튼", "스냅", "없음", "모르겠음"]
OPENABLE = ["yes", "no", "unknown"]
LAYERS = ["얇음", "보통", "두꺼움", "모르겠음"]
WORN = ["yes", "no", "unknown"]
# 사진을 못 봤을 때의 값. ★ 빈칸이 아니라 "모른다" 다 — 아래 fit.prune_options 가
#   "모르면 연출을 빼지도 넣지도 않는다" 를 이 값으로 판단한다.
UNKNOWN = {"slot": AUTO, "closure": "모르겠음", "openable": "unknown", "layer": "모르겠음",
           "worn": "unknown", "box": [], "head": []}


def _inspect_schema():
    """★ strict 모드는 중첩 객체에도 additionalProperties:false 와 required 전부
    나열을 요구한다(llm.strict_schema 주석). 그래서 손으로 짠다."""
    from . import llm
    row = {"type": "object", "additionalProperties": False,
           "properties": {"slot": {"type": "string", "enum": SLOTS + [AUTO]},
                          "closure": {"type": "string", "enum": CLOSURES},
                          "openable": {"type": "string", "enum": OPENABLE},
                          "layer": {"type": "string", "enum": LAYERS},
                          "worn": {"type": "string", "enum": WORN},
                          "box": {"type": "array", "items": {"type": "number"}},
                          "head": {"type": "array", "items": {"type": "number"}}},
           "required": ["slot", "closure", "openable", "layer", "worn", "box", "head"]}
    return llm.strict_schema("feedit_vton_items",
                             {"items": {"type": "array", "items": row}}, ["items"])


def _ratio_box(value) -> list[float]:
    """[x0, y0, x1, y1] (0~1) 이 아니면 빈 목록. 너무 작은 상자도 버린다."""
    try:
        x0, y0, x1, y1 = (float(v) for v in value)
    except (TypeError, ValueError):
        return []
    x0, y0, x1, y1 = (max(0.0, min(1.0, v)) for v in (x0, y0, x1, y1))
    if x1 - x0 < 0.05 or y1 - y0 < 0.05:
        return []
    return [round(v, 4) for v in (x0, y0, x1, y1)]


def inspect(images: list[str], hints: list[str] | None = None) -> list[dict]:
    """사진 순서대로 {slot, closure, openable, layer, worn, box, head} 를 돌려준다.

    hints 는 사진마다 사용자가 고른 칸(없거나 '자동 분류' 면 모델이 판별) — 착용 컷에서
    어느 옷을 잘라 낼지(box) 정하는 데 쓴다.

    ★ 실패하면 전부 UNKNOWN 이다. 예전 classify() 가 못 판별한 사진을 '자동 분류' 로
      남겨 생성 프롬프트가 스스로 판별하게 넘긴 것과 같은 태도 — 모르는 것을 아는
      척하지 않는다.
    """
    from . import llm

    rows = [u for u in (images or []) if isinstance(u, str) and u.strip()][:MAX_ITEMS]
    fallback = [dict(UNKNOWN) for _ in rows]
    if not rows or not llm.available():
        return fallback
    content: list[dict] = [{"type": "input_text",
                            "text": "각 사진의 칸·여밈·두께·착용 여부와 영역을 순서대로 골라 주세요."}]
    hints = list(hints or [])
    for i, u in enumerate(rows):
        hint = hints[i] if i < len(hints) and hints[i] in SLOT_ORDER else ""
        content.append({"type": "input_text",
                        "text": f"{i + 1}번 사진" + (f" — 칸: {hint}" if hint else "")})
        content.append({"type": "input_image", "image_url": u})
    got = llm.respond(_INSPECT_INSTRUCTIONS, [{"role": "user", "content": content}],
                      _inspect_schema(), timeout=20, **llm.role("vision"))
    got_rows = (got or {}).get("items")
    if not isinstance(got_rows, list):
        return fallback
    out: list[dict] = []
    for i in range(len(rows)):
        row = got_rows[i] if i < len(got_rows) and isinstance(got_rows[i], dict) else {}
        slot = str(row.get("slot") or "")
        out.append({
            "slot": slot if slot in CATEGORIES else AUTO,
            "closure": row.get("closure") if row.get("closure") in CLOSURES else "모르겠음",
            "openable": row.get("openable") if row.get("openable") in OPENABLE else "unknown",
            "layer": row.get("layer") if row.get("layer") in LAYERS else "모르겠음",
            "worn": row.get("worn") if row.get("worn") in WORN else "unknown",
            "box": _ratio_box(row.get("box")),
            "head": _ratio_box(row.get("head")),
        })
    return out


def classify(images: list[str]) -> list[str]:
    """사진 순서대로 칸 이름만 돌려준다 — 화면의 칸 배치가 쓰는 값.

    ★ 판별은 inspect() 한 번으로 끝난다. 칸과 여밈을 따로 물으면 vision 호출이
      두 번이 된다(AGENTS.md §3 — 한 번에 받게 만든다).
    """
    return [row["slot"] for row in inspect(images)]
