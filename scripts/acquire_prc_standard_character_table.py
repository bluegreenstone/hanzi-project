#!/usr/bin/env python3
"""Acquire the official 2013 PRC standard-character table and its scanned PDF."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "source-data" / "prc-standard-characters-2013"
PAGE_URL = (
    "https://www.moe.gov.cn/jyb_sjzl/ziliao/A19/201306/"
    "t20130601_186002.html"
)
ZIP_URL = (
    "https://www.moe.gov.cn/publicfiles/business/htmlfiles/moe/"
    "cmsmedia/other/2013/7/other98742.zip"
)
ZIP_SHA256 = "45e2f58fc19260a0f578de3ff5e273c4d4e6b4bcdd9a1580059e191ab3c9bee3"
PDF_SHA256 = "af85c706a53d3b3bbad818bcce7415ac9a2284ea14f79fe7f54ce1248a7bdac9"
PDF_BYTES = 100_606_660


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "hanzi-project-source-audit/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page = fetch(PAGE_URL)
    archive_bytes = fetch(ZIP_URL)
    if sha256_bytes(archive_bytes) != ZIP_SHA256:
        raise RuntimeError("official character-table ZIP SHA-256 differs")

    archive_path = OUT / "tongyong-guifan-hanzi-biao-2013.zip"
    temp_archive = OUT / ".tongyong-guifan-hanzi-biao-2013.zip.tmp"
    temp_archive.write_bytes(archive_bytes)
    os.replace(temp_archive, archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        members = archive.namelist()
        if len(members) != 1:
            raise RuntimeError(f"expected one PDF member, got {members!r}")
        pdf = archive.read(members[0])
    if len(pdf) != PDF_BYTES or sha256_bytes(pdf) != PDF_SHA256:
        raise RuntimeError("official character-table PDF differs")
    pdf_path = OUT / "tongyong-guifan-hanzi-biao-2013.pdf"
    temp_pdf = OUT / ".tongyong-guifan-hanzi-biao-2013.pdf.tmp"
    temp_pdf.write_bytes(pdf)
    os.replace(temp_pdf, pdf_path)

    page_path = OUT / "official-download-page.html"
    page_path.write_bytes(page)
    retrieved_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    metadata = {
        "retrieved_at": retrieved_at,
        "official_page_url": PAGE_URL,
        "download_url": ZIP_URL,
        "page": {
            "local_path": str(page_path.relative_to(ROOT)),
            "sha256": sha256_bytes(page),
            "bytes": len(page),
        },
        "archive": {
            "local_path": str(archive_path.relative_to(ROOT)),
            "sha256": ZIP_SHA256,
            "bytes": len(archive_bytes),
            "member_name_as_decoded_by_zipfile": members[0],
        },
        "document": {
            "local_path": str(pdf_path.relative_to(ROOT)),
            "sha256": PDF_SHA256,
            "bytes": PDF_BYTES,
            "pages": 137,
        },
    }
    (OUT / "acquisition.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
