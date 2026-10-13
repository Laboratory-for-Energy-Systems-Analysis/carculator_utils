"""Restore direct vehicle intensities in the four locally installed REMIND files.

Preserve encrypted backups and all existing plaintext bytes. Refuse source
version mismatches or repeated installations; write hashes and counts only.
"""

import ast
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pandas as pd
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]
PREMISE = ROOT / "premise"
sys.path.insert(0, str(PREMISE))
from scripts.restore_vehicle_intensities import (
    append_intensity_rows,
    mapped_intensities,
)

ORIGINALS = Path("/Users/romain/Library/CloudStorage/Dropbox/Notebooks/IAM-ecoinvent")
WORK = Path("/private/tmp/premise-vehicle-intensity-20261013")
OUTPUT = ROOT / "carculator_utils/results/premise_vehicle_intensity_20261013"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = OUTPUT / "installation.json"
    if manifest.exists():
        raise RuntimeError("Installation already recorded; do not overwrite provenance")
    key = os.environ.get("PREMISE_KEY")
    if not key:
        skill = Path("/Users/romain/.codex/skills/premise/SKILL.md").read_text()
        key = re.search(r"```text\s+([^\s]+)\s+```", skill).group(1)
    cipher = Fernet(key.encode())
    (WORK / "before").mkdir(parents=True, exist_ok=True)
    (WORK / "candidates").mkdir(exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    aliases = mapped_intensities("remind")
    records = []
    paths = sorted((PREMISE / "premise/data/iam_output_files").glob("remind_*.csv"))
    for path in paths:
        pathway = path.stem.removeprefix("remind_")
        original_pathway = pathway + "2025" if pathway.endswith("NPi") else pathway
        original = ORIGINALS / f"remind 3.5.2/REMIND_generic_{original_pathway}.mif"
        encrypted = path.read_bytes()
        restored, record = append_intensity_rows(
            cipher.decrypt(encrypted), pd.read_csv(original, sep=";"), aliases
        )
        if record["appended_rows"] == 0:
            raise RuntimeError(f"{path.name} already contains intensity rows")
        backup = WORK / "before" / path.name
        candidate = WORK / "candidates" / path.name
        if backup.exists() or candidate.exists():
            raise RuntimeError("Private backup/candidate already exists")
        shutil.copy2(path, backup)
        candidate.write_bytes(cipher.encrypt(restored))
        assert cipher.decrypt(candidate.read_bytes()) == restored
        record.update(
            filename=path.name,
            original=str(original.relative_to(ORIGINALS)),
            original_sha256=digest(original),
            before_sha256=digest(backup),
            after_sha256=digest(candidate),
        )
        records.append(record)
    # Complete all source/version checks before installing any candidate.
    for record in records:
        path = PREMISE / "premise/data/iam_output_files" / record["filename"]
        assert digest(path) == record["before_sha256"]
    for record in records:
        path = PREMISE / "premise/data/iam_output_files" / record["filename"]
        shutil.copy2(WORK / "candidates" / path.name, path)
        assert digest(path) == record["after_sha256"]

    notebook = ORIGINALS / "encryption/encryption.ipynb"
    raw = notebook.read_text()
    before = json.loads(raw)
    cell = before["cells"][6]
    line = next(line for line in cell["source"] if line.strip() == '"Efficiency",')
    needle = json.dumps(line)
    assert raw.count(needle) == 1
    offset = raw.index(needle)
    prefix = raw[raw.rfind("\n", 0, offset) + 1 : offset]
    replacement = needle + ",\n" + prefix + json.dumps('    "Energy intensity",\n')
    changed = raw.replace(needle, replacement, 1)
    after = json.loads(changed)
    source = "".join(after["cells"][6]["source"])
    ast_tree = ast.parse(source)
    prefixes = next(
        ast.literal_eval(node.value)
        for node in ast_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "l_var" for t in node.targets)
    )
    assert any("Energy intensity|Transport|Car|BEV".startswith(p) for p in prefixes)
    expected = json.loads(raw)
    expected["cells"][6]["source"].insert(
        expected["cells"][6]["source"].index(line) + 1, '    "Energy intensity",\n'
    )
    assert expected == after
    shutil.copy2(notebook, WORK / "before/encryption.ipynb")
    notebook.write_text(changed)
    document = {
        "script_sha256": digest(Path(__file__)),
        "scenarios": records,
        "notebook": {
            "path": str(notebook.relative_to(ORIGINALS)),
            "before_sha256": digest(WORK / "before/encryption.ipynb"),
            "after_sha256": digest(notebook),
            "changed_cell": 6,
            "change": "Add Energy intensity to retained variable prefixes",
            "validation": "JSON and cell AST parsed; whitelist evaluated in isolation",
            "full_notebook_executed": False,
        },
    }
    manifest.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({r["filename"]: r["appended_rows"] for r in records}))


if __name__ == "__main__":
    main()
