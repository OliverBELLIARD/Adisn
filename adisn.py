"""Adisn command entrypoint.

Usage:
  python -m adisn
  python -m adisn status
  python -m adisn tool --tool-flag --tool-action status
"""

from harness.cli.main import main


if __name__ == "__main__":
    main()
