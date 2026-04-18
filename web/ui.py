"""兼容：uvicorn web.ui:app（页面与路由在 main.py）。"""
from main import app

__all__ = ["app"]
