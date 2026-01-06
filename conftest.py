import sys
from pathlib import Path


def pytest_configure() -> None:
    # Ensure `src/` is on sys.path for tests without installation.
    src_dir = (Path(__file__).parent / "src").resolve()
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
