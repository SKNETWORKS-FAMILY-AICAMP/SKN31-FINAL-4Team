from __future__ import annotations

from pathlib import Path
import os
import sys


def setup_django() -> Path:
    """
    Streamlit/Jupyter에서 FEEDIT Django 프로젝트를 사용할 수 있게 초기화한다.
    """
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

    cwd = Path.cwd()

    candidates = [
        cwd,
        cwd.parent,
        cwd.parent.parent,
        Path(r"C:\SKN31-FINAL-4Team\backend"),
    ]

    backend_dir = None

    for candidate in candidates:
        if (candidate / "manage.py").exists():
            backend_dir = candidate
            break

    if backend_dir is None:
        raise FileNotFoundError(
            "manage.py를 찾지 못했습니다. "
            "C:\\SKN31-FINAL-4Team\\backend 또는 현재 실행 위치를 확인하세요."
        )

    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    os.chdir(backend_dir)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django
    django.setup()

    return backend_dir
