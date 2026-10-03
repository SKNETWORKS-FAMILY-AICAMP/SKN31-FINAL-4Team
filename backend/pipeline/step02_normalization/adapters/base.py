from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseNormalizationAdapter(ABC):
    source_code: str = ""

    @abstractmethod
    def build(self, product_source) -> dict[str, Any]:
        raise NotImplementedError
