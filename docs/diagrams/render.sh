#!/usr/bin/env bash
# Render all Mermaid .mmd files to SVG via mermaid.ink API.
# Inject an explicit white background into the SVG output for dark-theme previews.
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


def add_white_background(svg: str) -> str:
    """Insert an explicit white background behind Mermaid SVG content."""
    svg_open = svg.find("<svg")
    if svg_open == -1:
        return svg
    svg_close = svg.find(">", svg_open)
    if svg_close == -1:
        return svg
    background = '<rect width="100%" height="100%" fill="white"/>'
    if background in svg[:svg_close + 1]:
        return svg
    return svg[:svg_close + 1] + background + svg[svg_close + 1:]

for mmd_file in sorted(pathlib.Path(".").glob("*.mmd")):
    svg_file = mmd_file.with_suffix(".svg")
    text = mmd_file.read_text()
    encoded = base64.urlsafe_b64encode(text.encode()).decode()
    r = requests.get(f"https://mermaid.ink/svg/{encoded}?bgColor=white", timeout=30)
    if r.status_code == 200 and "svg" in r.headers.get("content-type", ""):
        svg = add_white_background(r.text)
        svg_file.write_text(svg)
        print(f"OK  {svg_file.name}  ({len(r.content)//1024}KB)")
    else:
        print(f"FAIL {mmd_file.name}: HTTP {r.status_code}")

print("Done.")
EOF
