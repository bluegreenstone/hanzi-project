#!/usr/bin/env python3
"""Parse pinned Commons radical historical-form indexes deterministically."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = (
    ROOT
    / "source-data"
    / "wikimedia-2026-08-10"
    / "commons-acc-radical-historical-indexes.json"
)
OUTPUT = (
    ROOT
    / "source-data"
    / "wikimedia-2026-08-10"
    / "commons-acc-radical-historical-candidates.json"
)
PROJECT_KIND = {
    "Commons:Ancient Chinese characters/oracle": "oracle_bone_甲骨文",
    "Commons:Ancient Chinese characters/bronze": "bronze_金文",
    "Commons:Ancient Chinese characters/bigseal": "liushutong_六書通",
}
RADICAL_TITLE = re.compile(r"^Category:Radical (\d{3})$")


class RadicalIndexParser(HTMLParser):
    """Extract the first explicit file or missing-file link after each radical."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.active_number: int | None = None
        self.records: dict[int, dict[str, str | int]] = {}

    def handle_starttag(
        self, tag: str, attrs_list: list[tuple[str, str | None]]
    ) -> None:
        if tag != "a":
            return
        attrs = dict(attrs_list)
        title = attrs.get("title") or ""
        match = RADICAL_TITLE.fullmatch(title)
        if match:
            number = int(match.group(1))
            if number in self.records:
                raise ValueError(f"duplicate radical table position {number:03d}")
            self.active_number = number
            return
        if self.active_number is None or self.active_number in self.records:
            return
        href = attrs.get("href") or ""
        classes = set((attrs.get("class") or "").split())
        if "mw-file-description" in classes and href.startswith("/wiki/File:"):
            source_file = urllib.parse.unquote(href.removeprefix("/wiki/File:"))
            self.records[self.active_number] = {
                "kangxi_number": self.active_number,
                "status": "candidate",
                "source_file": source_file,
            }
        elif "new" in classes and title.startswith("File:"):
            self.records[self.active_number] = {
                "kangxi_number": self.active_number,
                "status": "project_missing",
                "unfilled_filename": title.removeprefix("File:"),
            }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    radicals = {
        number: json.loads((ROOT / "radicals" / f"{number}.json").read_text())
        for number in range(1, 215)
    }
    pages: list[dict[str, object]] = []
    all_records: list[dict[str, object]] = []
    for page in source["rendered_pages"]:
        title = page["title"]
        if title not in PROJECT_KIND:
            raise ValueError(f"unexpected project page {title!r}")
        parser = RadicalIndexParser()
        parser.feed(page["parse"]["text"])
        expected_numbers = set(range(1, 215))
        if set(parser.records) != expected_numbers:
            missing = sorted(expected_numbers - set(parser.records))
            extra = sorted(set(parser.records) - expected_numbers)
            raise ValueError(f"{title}: radical positions missing={missing}, extra={extra}")
        kind = PROJECT_KIND[title]
        candidates = 0
        missing = 0
        for number in range(1, 215):
            record = parser.records[number]
            record.update(
                {
                    "primary": radicals[number]["primary"]["char"],
                    "radical_block": radicals[number]["radical_block"]["char"],
                    "kind": kind,
                    "mapping_method": "pinned_commons_project_radical_table",
                    "source_id": source["source_id"],
                    "source_page": title,
                    "source_page_id": page["page_id"],
                    "source_revision_id": page["revision_id"],
                }
            )
            if record["status"] == "candidate":
                candidates += 1
            else:
                missing += 1
            all_records.append(record)
        pages.append(
            {
                "title": title,
                "page_id": page["page_id"],
                "revision_id": page["revision_id"],
                "kind": kind,
                "candidate_count": candidates,
                "project_missing_count": missing,
            }
        )
    payload = {
        "source_id": source["source_id"],
        "input_path": str(INPUT.relative_to(ROOT)),
        "input_sha256": sha256(INPUT),
        "method": (
            "Explicit file links and unfilled-file links following numbered radical "
            "positions in pinned Commons project-page HTML; no visual matching."
        ),
        "absence_policy": (
            "project_missing means only that the pinned project table has no file; "
            "it is not evidence of historical non-attestation."
        ),
        "pages": pages,
        "records": sorted(
            all_records, key=lambda item: (item["kangxi_number"], item["kind"])
        ),
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    for page in pages:
        print(
            f"{page['kind']}: {page['candidate_count']} candidates, "
            f"{page['project_missing_count']} project-missing"
        )


if __name__ == "__main__":
    main()
