from __future__ import annotations

import sys


def main() -> int:
    try:
        from focus_guard.gui import run_app
    except ModuleNotFoundError as exc:
        missing = exc.name or "a required package"
        print(
            f"Focus Guard could not start because '{missing}' is missing.\n\n"
            "Run setup_and_run.bat, or install the dependencies with:\n"
            "  python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
