"""Extract the exact tagged version's changelog for the GitHub Release body."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import uuid


def extract_release_notes(changelog: str, version: str) -> str:
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
        raise ValueError("Expected an exact MAJOR.MINOR.PATCH version")
    pattern = rf"^## \[v{re.escape(version)}\][^\r\n]*\r?\n(.*?)(?=^## \[v|\Z)"
    match = re.search(pattern, changelog, re.MULTILINE | re.DOTALL)
    if match is None:
        raise ValueError(f"CHANGELOG.md is missing v{version}")
    body = re.sub(r"\s*---\s*$", "", match.group(1)).strip()
    if not body:
        raise ValueError(f"CHANGELOG.md has no notes for v{version}")
    return f"## Clock/Alarm v{version}\n\n{body}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    body = extract_release_notes(args.changelog.read_text(encoding="utf-8-sig"), args.version)
    if args.github_output:
        delimiter = "release_notes_" + uuid.uuid4().hex
        with args.github_output.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"body<<{delimiter}\n{body}\n{delimiter}\n")
    else:
        print(body)


if __name__ == "__main__":
    main()
