"""FEEDIT dashboard view package.

기존 urls.py에서 `from . import views` 후
`views.some_view`를 사용하던 공개 이름을 그대로 유지한다.
"""

from .home import *
from .collection import *
from .normalization import *
from .dictionary import *
from .data import *
from .analytics import *
from .brand_mapping import *
from .system import *
from .analytics import (
    term_metrics,
    trend_metrics,
    product_metrics,
    product_snapshot,
    product_snapshot_detail,
    text_comment_metrics,
)