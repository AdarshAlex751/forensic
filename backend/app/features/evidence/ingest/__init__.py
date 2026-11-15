"""Evidence ingest: case folder -> events.json, evidence.json, case.json (data/evidence/FORMAT.md).

  ingest.py     orchestrates: custody check, one parser per file (registry.py), sort, ids e1..
  base.py       the parser contract (FileCtx in, event dicts out) and shared helpers
  custody.py    sha256 of every file vs manifest.csv -> evidence.json rows
  registry.py   which parser handles which file path
  csv_parsers.py, doc_parsers.py   the parsers

The parsers read only what is inside the case folder (including its own facilities/devices.csv). They must never
import the case generator (casegen/) or read data/evidence/truth/ or answer_key.json: they have to work on any
evidence folder in this format, not just the one we generated.
"""
