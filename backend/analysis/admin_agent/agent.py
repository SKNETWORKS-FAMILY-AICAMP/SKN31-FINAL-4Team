from __future__ import annotations

import os
import uuid
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from .prompts import SYSTEM_PROMPT
from .tools import ALL_TOOLS


DEFAULT_MODEL = os.getenv(
    "FEEDIT_ADMIN_AGENT_MODEL",
    "openai:gpt-5.4",
)

# MVP: 서버 프로세스가 살아있는 동안 thread state 유지.
# 운영 배포에서는 PostgresSaver로 교체 권장.
CHECKPOINTER = InMemorySaver()


def build_agent():
    """
    LangChain create_agent는 내부적으로 LangGraph runtime을 사용한다.
    쓰기 Tool 3개는 Human-in-the-loop interrupt 대상이다.

    LangSmith는 환경변수만 설정하면 자동 tracing 된다:
        LANGSMITH_TRACING=true
        LANGSMITH_API_KEY=...
        LANGSMITH_PROJECT=feedit-admin-agent
    """
    return create_agent(
        model=DEFAULT_MODEL,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "create_alias": {
                        "allowed_decisions": [
                            "approve",
                            "reject",
                        ],
                    },
                    "create_term": {
                        "allowed_decisions": [
                            "approve",
                            "reject",
                        ],
                    },
                    "add_discovery_exclusion": {
                        "allowed_decisions": [
                            "approve",
                            "reject",
                        ],
                    },
                },
                description_prefix=(
                    "FEEDIT DB 변경 작업은 관리자 승인이 필요합니다."
                ),
            ),
        ],
        checkpointer=CHECKPOINTER,
    )


AGENT = build_agent()


def new_thread_id() -> str:
    return f"feedit-admin-{uuid.uuid4()}"


def _config(thread_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
        },
        "run_name": "feedit-admin-agent",
        "tags": [
            "feedit",
            "admin",
        ],
    }


def _message_content(message) -> str | None:
    if message is None:
        return None

    content = getattr(
        message,
        "content",
        None,
    )

    if isinstance(content, str):
        return content

    if content is None:
        return None

    return str(content)


def _normalize_result(
    result,
    *,
    thread_id: str,
) -> dict[str, Any]:
    """
    Django view에서 바로 JSONResponse로 내보내기 쉬운 구조.
    """
    value = getattr(
        result,
        "value",
        None,
    )

    if value is None and isinstance(
        result,
        dict,
    ):
        value = result

    messages = []

    if isinstance(value, dict):
        messages = value.get(
            "messages",
            [],
        ) or []

    final_message = (
        _message_content(messages[-1])
        if messages
        else None
    )

    raw_interrupts = getattr(
        result,
        "interrupts",
        (),
    ) or ()

    interrupts = []

    for item in raw_interrupts:
        interrupt_value = getattr(
            item,
            "value",
            item,
        )

        interrupts.append(
            interrupt_value
        )

    return {
        "thread_id": thread_id,
        "interrupted": bool(
            interrupts
        ),
        "interrupts": interrupts,
        "message": final_message,
    }


def ask_admin_agent(
    message: str,
    *,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """
    일반 질문/조회 시작.

    예:
        result = ask_admin_agent(
            "최근 PENDING 후보 10개 보여줘"
        )

    DB 변경 Tool이 필요하면 interrupted=True로 반환되고
    실제 변경은 아직 실행되지 않는다.
    """
    thread_id = (
        thread_id
        or new_thread_id()
    )

    result = AGENT.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": message,
                }
            ]
        },
        config=_config(thread_id),
        version="v2",
    )

    return _normalize_result(
        result,
        thread_id=thread_id,
    )


def resume_admin_agent(
    thread_id: str,
    *,
    approve: bool,
    message: str | None = None,
) -> dict[str, Any]:
    """
    pending write Tool을 승인/거절한다.

    approve=True:
        tool 실제 실행

    approve=False:
        tool 실행 안 함
    """
    if approve:
        decision = {
            "type": "approve",
        }
    else:
        decision = {
            "type": "reject",
            "message": (
                message
                or (
                    "관리자가 이 변경을 거절했습니다. "
                    "같은 변경을 자동 재시도하지 마세요."
                )
            ),
        }

    result = AGENT.invoke(
        Command(
            resume={
                "decisions": [
                    decision
                ]
            }
        ),
        config=_config(thread_id),
        version="v2",
    )

    return _normalize_result(
        result,
        thread_id=thread_id,
    )
