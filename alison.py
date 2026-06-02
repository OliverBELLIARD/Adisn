"""Alison command entrypoint.

Usage:
  python -m alison
  python -m alison status
  python -m alison tool --tool-flag --tool-action status
"""

from harness.cli.main import main


if __name__ == "__main__":
    main()
