"""저장소 루트의 `.env` 를 읽어 os.environ 에 채운다 — 표준 라이브러리만 쓴다.

★ 왜 python-dotenv 를 안 쓰나
  챗봇은 지금 표준 라이브러리로만 돈다(server.py 맨 위 참고).
  팀원이 `pip install` 하나 빠뜨렸다고 키를 못 읽는 상황을 만들지 않는다.
  Django 쪽은 이미 python-dotenv 를 쓰지만, 그건 그쪽 사정이다.

★ 이미 있는 환경변수를 덮어쓰지 않는다.
  셸이나 서비스 관리자가 넣어 준 값, 예를 들어 `OPENAI_API_KEY=... python3 server.py`
  로 준 값이 항상 이긴다. 파일은 **비어 있는 칸만** 채운다.

★ 값을 출력하지 않는다. 어느 파일을 읽었는지만 남긴다 (AGENTS.md §8).

찾는 순서
  ① 환경변수 FEEDIT_ENV_FILE 이 가리키는 파일
  ② ChatBot/.env
  ③ 저장소 루트 .env                 ← 팀 표준. 여기 하나로 모은다
  ④ 그 위 폴더의 .env
"""
from __future__ import annotations

import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # ChatBot/app
_CHATBOT = _HERE.parent                          # ChatBot
_REPO = _CHATBOT.parent                          # feedit

LOADED_FROM: list[str] = []


def _candidates() -> list[Path]:
    named = os.getenv("FEEDIT_ENV_FILE")
    out = [Path(named)] if named else []
    out += [_CHATBOT / ".env", _REPO / ".env", _REPO.parent / ".env"]
    return out


def _parse(text: str) -> dict[str, str]:
    """`KEY=VALUE` 만 읽는다. 셸 문법(치환·명령)은 해석하지 않는다."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if not k:
            continue
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k] = v
    return out


def load(*, override: bool = False) -> list[str]:
    """찾은 .env 를 전부 읽어 채운다. 읽은 파일 경로 목록을 돌려준다.

    앞에 오는 파일이 이긴다 — ChatBot/.env 로 개인 설정을 덮어쓸 수 있다.
    """
    if LOADED_FROM:
        return LOADED_FROM
    seen: set[Path] = set()
    for path in _candidates():
        try:
            path = path.resolve()
        except OSError:
            continue
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            # BOM 이 붙어 있어도(윈도우 메모장) 첫 키를 잃지 않는다
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        for k, v in _parse(text).items():
            if override or not os.environ.get(k):
                os.environ[k] = v
        LOADED_FROM.append(str(path))
    return LOADED_FROM


def where() -> str:
    """진단용 — 어느 파일을 읽었나. 값은 안 보여 준다."""
    return ", ".join(LOADED_FROM) if LOADED_FROM else "(없음)"
