from __future__ import annotations
from abc import ABC, abstractmethod
from .schemas import CollectionResult


class BasePlatformPipeline(ABC):

    SOURCE_CODE: str

    def run(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> CollectionResult:

        result = self.collect(
            target_type=target_type,
            target_url=target_url,
            params=params,
        )

        self.validate_result(result)

        return result

    def validate_result(
        self,
        result: CollectionResult,
    ) -> None:

        if not isinstance(
            result,
            CollectionResult,
        ):
            raise TypeError(
                f"{self.__class__.__name__}.collect() "
                "must return CollectionResult"
            )

        expected = self.SOURCE_CODE.upper().strip()
        actual = result.source_code.upper().strip()

        if actual != expected:
            raise ValueError(
                "source_code mismatch: "
                f"expected={expected}, "
                f"actual={actual}"
            )

    @abstractmethod
    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> CollectionResult:
        raise NotImplementedError
    
    