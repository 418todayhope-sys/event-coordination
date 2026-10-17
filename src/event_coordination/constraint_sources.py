"""Read-only supplementary source extraction for the reviewed constraint model."""

from datetime import datetime, timedelta
from pathlib import Path
import posixpath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from event_coordination.sources import read_evidence

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def workbook_rows(root: Path, capture: dict, sheet_name: str) -> list[dict]:
    """Decode stored cells, preserving original values and explicit date formats.

    Inputs have already been hash-verified through Stage 2. Formulas and unexpected
    date formats fail rather than being guessed or recalculated.
    """
    with ZipFile(root / capture["local_reference"]) as archive:
        if archive.testzip() is not None:
            raise ValueError("Invalid workbook ZIP")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall("s:sheets/s:sheet", NS)
        sheet = next(s for s in sheets if s.get("name") == sheet_name)
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in relationships if r.get("Id") == sheet.get(REL))
        part = posixpath.normpath(posixpath.join("xl", target))
        if not part.startswith("xl/worksheets/"):
            raise ValueError("Unexpected worksheet relationship")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(t.text or "" for t in item.findall(".//s:t", NS))
                       for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", NS)]
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        formats = {int(f.get("numFmtId")): f.get("formatCode")
                   for f in styles.findall("s:numFmts/s:numFmt", NS)}
        xfs = styles.findall("s:cellXfs/s:xf", NS)
        properties = workbook.find("s:workbookPr", NS)
        date1904 = properties is not None and properties.get("date1904") in ("1", "true")
        rows = []
        for row in ET.fromstring(archive.read(part)).findall("s:sheetData/s:row", NS):
            raw, values = {}, {}
            for cell in row.findall("s:c", NS):
                if cell.find("s:f", NS) is not None:
                    raise ValueError("Formula interpretation is not supported")
                node = cell.find("s:v", NS)
                value = node.text if node is not None else None
                if cell.get("t") == "s":
                    value = strings[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
                raw[cell.get("r")] = value
                fmt = int(xfs[int(cell.get("s", "0"))].get("numFmtId", "0"))
                if fmt >= 164:
                    if formats.get(fmt) != "yyyy-mm-dd":
                        raise ValueError("Unsupported custom cell format")
                    epoch = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
                    value = (epoch + timedelta(days=float(value))).date().isoformat()
                values[cell.get("r")] = value
            if any(v is not None for v in raw.values()):
                rows.append({"raw": raw, "values": values})
        return rows


def source_line(root: Path, path: str, line: int, expected: str) -> dict:
    """Supplement an upstream capture with a checked original line and hash."""
    record = read_evidence(root, "supplement", path, line, expected,
                           "Supplementary local source inspection; online equivalence unverified.")
    return {k: record[k] for k in ("path", "sha256", "line_start", "line_end", "excerpt", "provenance")}


def validate_dependencies(records: list[dict]) -> None:
    """Reject missing references and cycles in the proposed dependency graph."""
    graph = {r["id"]: r["depends_on_record_ids"] for r in records}
    visited, active = set(), set()

    def visit(identifier):
        if identifier not in graph:
            raise ValueError("Constraint dependency does not resolve")
        if identifier in active:
            raise ValueError("Constraint dependency cycle")
        if identifier in visited:
            return
        active.add(identifier)
        for dependency in graph[identifier]:
            visit(dependency)
        active.remove(identifier)
        visited.add(identifier)

    for identifier in graph:
        visit(identifier)
