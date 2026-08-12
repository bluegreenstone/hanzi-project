#!/usr/bin/env python3
"""Acquire and verify the pinned Taiwan MOE Concised Dictionary workbook."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path


URL = (
    "https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/"
    "respub/download/dict_concised_2014_20260626.zip"
)
ZIP_NAME = "dict_concised_2014_20260626.zip"
ZIP_SHA256 = "fc83d27eb3fbf6fcfdb791e7d05ef60946b58ef8e8857ed165b612217b392806"
ZIP_BYTES = 6_937_298
WORKBOOK_NAME = "dict_concised_2014_20260626.xlsx"
WORKBOOK_SHA256 = "a9a4fd7259180113bfae2e94110eae87ac4dcf0bfcc91a6437c3ad4773ab7865"
WORKBOOK_BYTES = 7_076_857


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, expected_hash: str, expected_bytes: int) -> None:
    if path.stat().st_size != expected_bytes:
        raise RuntimeError(
            f"unexpected byte length for {path.name}: {path.stat().st_size}"
        )
    actual_hash = sha256_path(path)
    if actual_hash != expected_hash:
        raise RuntimeError(
            f"unexpected SHA-256 for {path.name}: {actual_hash}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("source-data/moe-concised-2014-20260626"),
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / ZIP_NAME
    workbook_path = output_dir / WORKBOOK_NAME

    request = urllib.request.Request(URL, headers={"User-Agent": "hanzi-project-audit/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        with zip_path.open("wb") as stream:
            shutil.copyfileobj(response, stream)
    verify(zip_path, ZIP_SHA256, ZIP_BYTES)

    with zipfile.ZipFile(zip_path) as archive:
        members = archive.namelist()
        if members != [WORKBOOK_NAME]:
            raise RuntimeError(f"unexpected MOE ZIP members: {members}")
        with archive.open(WORKBOOK_NAME) as source, workbook_path.open("wb") as target:
            shutil.copyfileobj(source, target)
    verify(workbook_path, WORKBOOK_SHA256, WORKBOOK_BYTES)
    print(f"verified {zip_path}")
    print(f"verified {workbook_path}")


if __name__ == "__main__":
    main()
