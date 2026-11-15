#!/usr/bin/env python3
"""Verify original migrated resources without requiring the Godot checkout."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
assets = ROOT / "src/main/resources/assets"
manifest = json.loads((ROOT / "tools/reference/assets-sha256.json").read_text())
for relative, expected in manifest.items():
    path = assets / relative
    assert path.is_file(), f"Missing migrated resource: {relative}"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, relative
assert {str(p.relative_to(assets)) for p in assets.rglob("*") if p.is_file()} == set(
    manifest
)
rows = [
    line.split("\t")
    for line in (ROOT / "src/main/resources/levels.tsv").read_text().splitlines()
]
for kind, total in [("LEVEL", 20), ("ACORN", 60), ("GEM", 378), ("END", 20)]:
    assert sum(row[0] == kind for row in rows) == total, kind
print(
    f"PASS: {len(manifest)} original resources unchanged; 20 levels, 60 acorns, 378 gems."
)
