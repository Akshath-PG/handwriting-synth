#!/usr/bin/env bash
# End-to-end self test with NO human handwriting needed:
#   template -> fake phone photos (from the sample library) -> calibrate -> convert md/docx/pdf
set -euo pipefail
cd "$(dirname "$0")/.."
T=$(mktemp -d)
python3 src/handwrite.py template -o "$T/template.pdf"
python3 tests/simulate_photos.py "$T/template.pdf" examples/sample_library.pkl "$T/photos"
python3 src/handwrite.py calibrate "$T"/photos/photo_*.jpg -o "$T/lib.pkl" --debug "$T/debug"
python3 src/handwrite.py convert examples/demo.md      -o "$T/md.pdf"   --lib "$T/lib.pkl"
python3 src/handwrite.py convert tests/sample.docx     -o "$T/docx.pdf" --lib "$T/lib.pkl" --ink black
python3 src/handwrite.py convert examples/source_assignment.pdf -o "$T/pdf.pdf" --lib "$T/lib.pkl"
ls -la "$T"/*.pdf && echo "E2E OK (outputs in $T)"
