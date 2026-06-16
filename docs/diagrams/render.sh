#!/usr/bin/env bash
# Render all Mermaid .mmd files to SVG via mermaid.ink API.
# Run from docs/diagrams/: bash render.sh
# No dependencies beyond Python 3 + requests.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

python3 - <<'EOF'
import base64, pathlib, sys
try:
    import requests
except ImportError:
    print("Installing requests..."); import subprocess; subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

for mmd_file in sorted(pathlib.Path(".").glob("*.mmd")):
    svg_file = mmd_file.with_suffix(".svg")
    text = mmd_file.read_text()
    encoded = base64.urlsafe_b64encode(text.encode()).decode()
    r = requests.get(f"https://mermaid.ink/svg/{encoded}?bgColor=white", timeout=30)
    if r.status_code == 200 and "svg" in r.headers.get("content-type", ""):
        svg_file.write_bytes(r.content)
        print(f"OK  {svg_file.name}  ({len(r.content)//1024}KB)")
    else:
        print(f"FAIL {mmd_file.name}: HTTP {r.status_code}")

print("Done.")
EOF
