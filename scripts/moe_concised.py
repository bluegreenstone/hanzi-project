#!/usr/bin/env python3
"""Read pronunciation evidence from the official MOE Concised Dictionary XLSX."""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator


SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
CELL_REF_RE = re.compile(r"^([A-Z]+)[0-9]+$")
REQUIRED_COLUMNS = ("字詞名", "字詞號", "注音一式", "漢語拼音", "釋義")
XLSX_ESCAPE_RE = re.compile(r"_x([0-9A-Fa-f]{4})_")


def normalize(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).replace("\u3000", " ")
    return " ".join(text.split()).casefold()


def decode_xlsx_text(value: str) -> str:
    """Decode OOXML's `_xHHHH_` character escapes in a cell string."""
    return XLSX_ESCAPE_RE.sub(lambda match: chr(int(match.group(1), 16)), value)


def column_number(reference: str) -> int:
    match = CELL_REF_RE.fullmatch(reference)
    if not match:
        raise ValueError(f"invalid XLSX cell reference: {reference!r}")
    value = 0
    for character in match.group(1):
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    result: list[str] = []
    with archive.open("xl/sharedStrings.xml") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag == f"{{{SHEET_NS}}}si":
                result.append(
                    decode_xlsx_text(
                        "".join(
                            node.text or ""
                            for node in element.iter(f"{{{SHEET_NS}}}t")
                        )
                    )
                )
                element.clear()
    return result


def worksheet_rows(
    archive: zipfile.ZipFile, strings: list[str]
) -> Iterator[list[str | None]]:
    with archive.open("xl/worksheets/sheet1.xml") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag != f"{{{SHEET_NS}}}row":
                continue
            values: dict[int, str | None] = {}
            for cell in element.findall(f"{{{SHEET_NS}}}c"):
                index = column_number(cell.attrib["r"])
                value_node = cell.find(f"{{{SHEET_NS}}}v")
                value = value_node.text if value_node is not None else None
                if value is not None and cell.attrib.get("t") == "s":
                    value = strings[int(value)]
                values[index] = value
            width = max(values, default=-1) + 1
            yield [values.get(index) for index in range(width)]
            element.clear()


def load_moe_rows(path: Path) -> dict[str, list[dict[str, str]]]:
    with zipfile.ZipFile(path) as archive:
        strings = shared_strings(archive)
        rows = worksheet_rows(archive, strings)
        header = [normalize(value) for value in next(rows)]
        missing = sorted(set(REQUIRED_COLUMNS) - set(header))
        if missing:
            raise ValueError(f"MOE workbook is missing required columns: {missing}")
        column = {
            name: header.index(normalize(name)) for name in REQUIRED_COLUMNS
        }
        result: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            def get(name: str) -> str | None:
                index = column[name]
                return row[index] if index < len(row) else None

            term = unicodedata.normalize("NFC", str(get("字詞名") or "")).strip()
            zhuyin = normalize(get("注音一式"))
            pinyin = normalize(get("漢語拼音"))
            definition = str(get("釋義") or "")
            if not term or not zhuyin or not pinyin:
                continue
            if not definition:
                raise ValueError(f"MOE entry {get('字詞號')!r} has no definition")
            result[term].append(
                {
                    "entry_id": str(get("字詞號") or "").strip(),
                    "pinyin": pinyin,
                    "zhuyin": zhuyin,
                    "definition": definition,
                }
            )
    return dict(result)
