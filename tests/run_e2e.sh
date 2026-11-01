#!/usr/bin/env bash
# End-to-end self test with NO human handwriting needed:
#   template -> fake phone photos (from the sample library) -> calibrate -> convert md/docx/pdf
#   + a cursive template made for one document -> shuffled photos -> calibrate -> convert
set -euo pipefail
cd "$(dirname "$0")/.."
T=$(mktemp -d)
python3 src/handwrite.py template -o "$T/template.pdf"
python3 tests/simulate_photos.py "$T/template.pdf" examples/sample_library.pkl "$T/photos"
python3 src/handwrite.py calibrate "$T"/photos/photo_*.jpg -o "$T/lib.pkl" --debug "$T/debug"
python3 src/handwrite.py convert examples/demo.md      -o "$T/md.pdf"   --lib "$T/lib.pkl"
python3 src/handwrite.py convert tests/sample.docx     -o "$T/docx.pdf" --lib "$T/lib.pkl" --ink black
python3 src/handwrite.py convert examples/source_assignment.pdf -o "$T/pdf.pdf" --lib "$T/lib.pkl"
# a cursive template made for one document (words + a chart to trace), photos in shuffled order
python3 src/handwrite.py template --doc tests/figure_doc.md --style cursive -o "$T/doc_tpl.pdf"
python3 tests/simulate_photos.py "$T/doc_tpl.pdf" examples/sample_library.pkl "$T/photos2" 2 --shuffle
python3 src/handwrite.py calibrate "$T"/photos2/photo_*.jpg --template "$T/doc_tpl.json" -o "$T/lib_cursive.pkl"
python3 src/handwrite.py convert tests/figure_doc.md -o "$T/cursive.pdf" --lib "$T/lib_cursive.pkl" --human natural
ls -la "$T"/*.pdf && echo "E2E OK (outputs in $T)"
