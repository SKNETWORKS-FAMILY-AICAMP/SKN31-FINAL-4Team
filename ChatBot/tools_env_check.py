"""켜기 전 점검 — 무엇이 되고 무엇이 없는지 한 화면에 보여 준다.

    cd ChatBot
    python3 tools_env_check.py

★ 네트워크를 쓰지 않는다. 설정만 본다.
  실제로 모델을 불러 보려면 그 다음에 `python3 tools_llm_check.py` 를 돌린다.

★ 키 값을 절대 출력하지 않는다. 있나 없나와 길이뿐이다 (AGENTS.md §8).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import config, llm          # noqa: E402  — app 을 import 해야 .env 가 읽힌다
from app.env import where            # noqa: E402

OK, NO = "  ✔", "  ✘"


def main() -> int:
    print("═" * 62)
    print(" feedit-chat 환경 점검")
    print("═" * 62)

    print("\n[.env]")
    print(f"   읽은 파일: {where()}")
    if where() == "(없음)":
        print(NO, ".env 를 못 찾았습니다. 저장소 루트에서: cp .env.example .env")

    # ── 1. LLM ────────────────────────────────────────────
    print("\n[1] LLM — gpt-5.6-luna 결합")
    print(f"   모델      {llm.MODEL}")
    print(f"   엔드포인트 {llm.API}")
    print(f"   추론 강도  {llm.DEFAULT_EFFORT}")
    if llm.DISABLED:
        print(NO, "FEEDIT_LLM_DISABLED 가 켜져 있습니다 — LLM 을 부르지 않습니다.")
    if llm.MODEL not in ("gpt-5.6-luna",):
        print("  !", f"팀 표준은 gpt-5.6-luna 입니다. 지금은 {llm.MODEL} 입니다.")
    if llm._read_key():                                   # noqa: SLF001 - 진단 목적
        print(OK, f"키 {llm.key_hint()} — 출처: {llm.source_hint()}")
    else:
        print(NO, "키가 없습니다. .env 에 OPENAI_API_KEY 를 넣으세요.")
        print("      키가 없어도 챗봇은 규칙만으로 답합니다. 다만")
        print("      의도 분류·어투 다듬기·웹 검색 세 가지가 빠집니다.")

    # ── 2. 데이터 ─────────────────────────────────────────
    print("\n[2] 챗봇 데이터·코드")
    print(f"   FEEDIT_DATA_BACKEND  {config.DATA_BACKEND}")
    if config.DATA_BACKEND == "rds":
        print(f"   RDS  {__import__('os').getenv('DB_HOST','(없음)')}:{__import__('os').getenv('DB_PORT','5432')}")
    else:
        print(f"   FEEDIT_CRAWLER_DIR  {config.CRAWLER}")
    gaps = config.missing_inputs()
    if not gaps:
        print(OK, "RDS 연결 설정과 질문 추출 코드가 준비됐습니다."
              if config.DATA_BACKEND == "rds" else "SQLite 회귀 테스트 준비물이 모두 있습니다.")
    else:
        for g in gaps:
            print(NO, g)
        print("\n      위에 표시된 환경변수 또는 파일 경로를 .env에 채워 주세요.")

    # ── 3. 서버 ───────────────────────────────────────────
    print("\n[3] 챗봇 서버")
    import os
    host = os.getenv("FEEDIT_CHAT_HOST", "127.0.0.1")
    port = os.getenv("FEEDIT_CHAT_PORT", "8770")
    print(f"   http://{host}:{port}")
    if host not in ("127.0.0.1", "localhost"):
        print("  !", "인증이 없는 서버입니다. 0.0.0.0 은 도커 안에서만 쓰세요.")

    # ── 정리 ──────────────────────────────────────────────
    print("\n" + "─" * 62)
    if gaps:
        print(" 지금 상태: 엔진을 켤 수 없습니다 (데이터 연결 설정 필요).")
        print(" 다음 할 일: 위 [2] 를 채우고 다시 돌리세요.")
        return 1
    print(" 지금 상태: 켤 수 있습니다.")
    print(" 다음 할 일: python3 tools_llm_check.py   (실제로 모델을 한 번 불러 봅니다)")
    print("             python3 server.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
