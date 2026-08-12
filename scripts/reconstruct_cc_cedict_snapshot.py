#!/usr/bin/env python3
"""Reconstruct the pinned CC-CEDICT content from its moving export.

The original 2026-08-11 gzip container was not retained locally, while the
registry did retain both its uncompressed SHA-256 and exact export header.  The
official editor change log identifies the nine changes made between that
header (log 97036) and the recovered live export (log 97045).  Reversing those
changes reproduces the recorded uncompressed bytes exactly.  The result is
stored in a new deterministic gzip container; both the unavailable original
container digest and this reconstructed-container digest remain documented.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path("source-data/cc-cedict-2026-08-11")
LIVE_PATH = SOURCE_ROOT / "cedict_live_20260812T000144Z.txt.gz"
OUTPUT_PATH = SOURCE_ROOT / "cedict_1_0_ts_utf-8_editor_20260811.txt.gz"
CHANGE_LOG_PATH = SOURCE_ROOT / "change-log-after-pinned-snapshot.html"
REPORT_PATH = SOURCE_ROOT / "reconstruction.json"

LIVE_GZIP_SHA256 = "8321ee502d588110abc87cd8ebaf3f1ba263d19a3646df45b1592609b3557f13"
LIVE_GZIP_BYTES = 3_967_662
LIVE_TEXT_SHA256 = "8ce48f5b50716148154508781aab93b24b17b492124d4ebb501be4d0b9fbbc76"
LIVE_TEXT_BYTES = 9_830_534
CHANGE_LOG_SHA256 = "5a0dab11bcf902eeb933a7185942de9894b0eac963ff5a4f14b55cf62e5bb893"
CHANGE_LOG_BYTES = 106_617
PINNED_ORIGINAL_GZIP_SHA256 = "73af18e207d9ae969e8f5d6b13c777bed64246268efb218e8df6d2f20563618f"
PINNED_ORIGINAL_GZIP_BYTES = 3_967_602
PINNED_TEXT_SHA256 = "147f106712fe0787741530a77f86f02b8ddd8929c2796f323eba705384064bae"
PINNED_TEXT_BYTES = 9_830_336
RECONSTRUCTED_GZIP_SHA256 = "fe1000b683609cde2ff7f70ee41541c47e44d8226f79ad209cf68138064865d4"
RECONSTRUCTED_GZIP_BYTES = 3_967_806

HEADER_REPLACEMENTS = {
    "#! entries=124820": "#! entries=124816",
    "#! date=2026-08-12T00:01:44Z": "#! date=2026-08-11T14:10:23Z",
    "#! time=1786492904": "#! time=1786457423",
}
REMOVE = [
    "長命 长命 [chang2 ming4] /long-lived/",
    "脈序 脉序 [mai4 xu4] /venation; pattern of veins on a leaf or insect wing/",
    "糖甙 糖甙 [tang2 dai4] /(dated) glycoside/",
    "堪達罕 堪达罕 [kan1 da2 han3] /(dialect) moose (loanword via Manchu)/",
    "一刻鐘 一刻钟 [yi1 ke4 zhong1] /a quarter of an hour/",
    "一刻 一刻 [yi1 ke4] /a quarter of an hour; 15 minutes/a moment; an instant/",
]
REPLACE = {
    "葉脈 叶脉 [ye4 mai4] /venation; pattern of veins on a leaf/": (
        "葉脈 叶脉 [ye4 mai4] /venation (pattern of veins on a leaf)/"
    ),
    "閒置 闲置 [xian2 zhi4] /to be left unused; to lie idle/": (
        "閒置 闲置 [xian2 zhi4] /to leave sth unused/to lie idle/"
    ),
    "大棚 大棚 [da4 peng2] /greenhouse; polytunnel/": (
        "大棚 大棚 [da4 peng2] /greenhouse/polytunnel/"
    ),
    "糖苷 糖苷 [tang2 gan1] /glycoside/": (
        "糖苷 糖苷 [tang2 gan1] /glucoside/"
    ),
    "甙 甙 [dai4] /(dated) glycoside (old term for 糖苷[tang2 gan1])/": (
        "甙 甙 [dai4] /old term for 糖苷[tang2 gan1], glycoside/"
    ),
}
ADD = [
    "列克星頓 列克星顿 [Lie4 ke4 xing1 dun4] /Lexington, Massachusetts/",
    (
        "葉脈序 叶脉序 [ye4 mai4 xu4] /leaf venation (botany)/"
        "the pattern of veins on a leaf, characteristic of each species/"
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if the reconstructed container or report is stale.",
    )
    return parser.parse_args()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def checked_bytes(path: Path, digest: str, size: int) -> bytes:
    payload = path.read_bytes()
    if len(payload) != size or sha256(payload) != digest:
        raise RuntimeError(f"pinned evidence differs: {path}")
    return payload


def reconstruct(live_text: bytes) -> bytes:
    if b"\r\n" not in live_text:
        raise RuntimeError("live export is not the expected CRLF text")
    lines = live_text.decode("utf-8").split("\r\n")
    if lines[-1] == "":
        raise RuntimeError("live export unexpectedly has a final CRLF")
    lines = [HEADER_REPLACEMENTS.get(line, line) for line in lines]

    for value in REMOVE:
        if lines.count(value) != 1:
            raise RuntimeError(f"post-snapshot addition is not unique: {value}")
        lines.remove(value)
    for current, prior in REPLACE.items():
        if lines.count(current) != 1:
            raise RuntimeError(f"post-snapshot replacement is not unique: {current}")
        lines[lines.index(current)] = prior

    header = [line for line in lines if line.startswith("#")]
    data = [line for line in lines if not line.startswith("#")]
    heads = [line.split(" ", 1)[0] for line in data]
    if any(left > right for left, right in zip(heads, heads[1:])):
        raise RuntimeError("live export headwords are not ascending")
    for value in ADD:
        headword = value.split(" ", 1)[0]
        index = bisect.bisect_right(heads, headword)
        data.insert(index, value)
        heads.insert(index, headword)
    if len(data) != 124_816:
        raise RuntimeError(f"reconstructed entry count differs: {len(data)}")
    result = "\r\n".join([*header, *data]).encode("utf-8")
    if len(result) != PINNED_TEXT_BYTES or sha256(result) != PINNED_TEXT_SHA256:
        raise RuntimeError("reconstructed text does not match the pinned digest")
    return result


def deterministic_gzip(payload: bytes) -> bytes:
    process = subprocess.run(
        ["gzip", "-n", "-9", "-c"],
        input=payload,
        capture_output=True,
        check=True,
    )
    result = process.stdout
    if (
        len(result) != RECONSTRUCTED_GZIP_BYTES
        or sha256(result) != RECONSTRUCTED_GZIP_SHA256
    ):
        raise RuntimeError("local deterministic gzip implementation differs")
    return result


def report() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "source_id": "cc-cedict-editor-2026-08-11",
        "status": "exact_uncompressed_snapshot_reconstructed",
        "pinned_export_header": {
            "entries": 124_816,
            "date": "2026-08-11T14:10:23Z",
            "time": 1_786_457_423,
            "last_included_change_log_id": 97036,
        },
        "recovered_live_export": {
            "path": str(LIVE_PATH),
            "gzip_sha256": LIVE_GZIP_SHA256,
            "gzip_bytes": LIVE_GZIP_BYTES,
            "text_sha256": LIVE_TEXT_SHA256,
            "text_bytes": LIVE_TEXT_BYTES,
            "last_included_change_log_id": 97045,
        },
        "official_change_log": {
            "url": "https://cc-cedict.org/editor/editor.php?handler=ListChanges",
            "path": str(CHANGE_LOG_PATH),
            "sha256": CHANGE_LOG_SHA256,
            "bytes": CHANGE_LOG_BYTES,
            "reversed_log_ids": list(range(97037, 97046)),
        },
        "original_container_not_recovered": {
            "recorded_sha256": PINNED_ORIGINAL_GZIP_SHA256,
            "recorded_bytes": PINNED_ORIGINAL_GZIP_BYTES,
        },
        "reconstructed_text": {
            "sha256": PINNED_TEXT_SHA256,
            "bytes": PINNED_TEXT_BYTES,
            "verification": "exactly matches the digest recorded at original acquisition",
        },
        "deterministic_container": {
            "path": str(OUTPUT_PATH),
            "sha256": RECONSTRUCTED_GZIP_SHA256,
            "bytes": RECONSTRUCTED_GZIP_BYTES,
            "command": "gzip -n -9 -c",
        },
    }


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    live_gzip = checked_bytes(
        root / LIVE_PATH, LIVE_GZIP_SHA256, LIVE_GZIP_BYTES
    )
    live_text = gzip.decompress(live_gzip)
    if len(live_text) != LIVE_TEXT_BYTES or sha256(live_text) != LIVE_TEXT_SHA256:
        raise RuntimeError("recovered live export text differs")
    checked_bytes(root / CHANGE_LOG_PATH, CHANGE_LOG_SHA256, CHANGE_LOG_BYTES)
    text = reconstruct(live_text)
    container = deterministic_gzip(text)
    expected_report = report()
    output_path = root / OUTPUT_PATH
    report_path = root / REPORT_PATH
    stale = not output_path.is_file() or output_path.read_bytes() != container
    report_stale = (
        not report_path.is_file()
        or json.loads(report_path.read_text(encoding="utf-8")) != expected_report
    )
    if not args.check:
        output_path.write_bytes(container)
        report_path.write_text(
            json.dumps(expected_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "text_sha256": sha256(text),
                "container_sha256": sha256(container),
                "container_stale": stale,
                "report_stale": report_stale,
                "mode": "check" if args.check else "write",
            },
            sort_keys=True,
        )
    )
    if args.check and (stale or report_stale):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
