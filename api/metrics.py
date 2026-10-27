import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import ApiHandler  # noqa: E402


class handler(ApiHandler):
    pass
