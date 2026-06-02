"""One-off rebrand: Alison -> Adisn in text files."""

from __future__ import annotations

from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", ".harness_snapshots", "node_modules"}
SKIP_FILES = {"alison.py", "alison.cmd", "rename_to_adisn.py"}

REPLACEMENTS = [
    ("ALISON_OLLAMA_MODEL", "ADISN_OLLAMA_MODEL"),
    ("ALISON_NO_BANNER", "ADISN_NO_BANNER"),
    ("ALISON_VERSION", "ADISN_VERSION"),
    ("_alison_ctrl_c_reset_hook", "_adisn_ctrl_c_reset_hook"),
    ("hello-alison", "hello-adisn"),
    ("Alison Code", "Adisn Code"),
    ("Exiting Alison.", "Exiting Adisn."),
    ("Alison interactive mode", "Adisn interactive mode"),
    ("Alison runtime", "Adisn runtime"),
    ("Alison CLI", "Adisn CLI"),
    ("Alison harness", "Adisn harness"),
    ("Alison repository", "Adisn repository"),
    ("You are Alison", "You are Adisn"),
    ("for Alison", "for Adisn"),
    ("from Alison", "from Adisn"),
    ("invoke Alison", "invoke Adisn"),
    ("Alison checks", "Adisn checks"),
    ("Alison probes", "Adisn probes"),
    ("# Alison\n", "# Adisn\n"),
    ("Alison is", "Adisn is"),
    ("Alison -", "Adisn -"),
    ('prog="alison"', 'prog="adisn"'),
    ("-m alison", "-m adisn"),
    ("alison.cmd", "adisn.cmd"),
    ("<ansicyan>alison</ansicyan>", "<ansicyan>adisn</ansicyan>"),
    (" alison >", " adisn >"),
    ("alison_left", "adisn_left"),
    ("/path/to/Alison", "/path/to/Adisn"),
    ("hello alison", "hello adisn"),
    ('"alison"', '"adisn"'),
    ("Alison/", "Adisn/"),
    ("Alison.", "Adisn."),
    ("Alison,", "Adisn,"),
    ("Alison\n", "Adisn\n"),
    ("Alison ", "Adisn "),
]


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    changed: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path.suffix in {".pyc", ".bak"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        orig = text
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            changed.append(str(path.relative_to(root)))
    print(f"Updated {len(changed)} files")
    for name in sorted(changed):
        print(name)


if __name__ == "__main__":
    main()
