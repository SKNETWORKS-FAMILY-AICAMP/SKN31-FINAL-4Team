from __future__ import annotations

from typing import Type

from .pipeline import BasePlatformPipeline


_PIPELINES: dict[
    str,
    Type[BasePlatformPipeline],
] = {}


def register_pipeline(
    source_code: str,
    pipeline_class: Type[BasePlatformPipeline],
) -> None:
    code = source_code.upper().strip()

    if not code:
        raise ValueError(
            "source_code is required"
        )

    _PIPELINES[code] = pipeline_class


def get_pipeline_class(
    source_code: str,
) -> Type[BasePlatformPipeline]:
    code = source_code.upper().strip()

    pipeline_class = _PIPELINES.get(
        code
    )

    if pipeline_class is None:
        supported = ", ".join(
            sorted(
                _PIPELINES.keys()
            )
        )

        raise ValueError(
            f"지원하지 않는 source입니다: {code}. "
            f"등록된 source: {supported or '없음'}"
        )

    return pipeline_class


def get_registered_sources() -> list[str]:
    return sorted(
        _PIPELINES.keys()
    )