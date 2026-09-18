"""Deprecated compatibility shim.

Dashboard 공용 helper의 실제 구현은 helpers.py에만 둔다.
기존 코드의 `from ._common import *` 호환을 위해 재-export한다.
"""

from .helpers import *  # noqa: F401,F403
from .helpers import __all__
