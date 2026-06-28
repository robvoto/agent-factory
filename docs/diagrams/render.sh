#!/usr/bin/env bash
# Render all Mermaid .mmd files to SVG using local jsdom + Mermaid.
# Run from docs/diagrams/: bash render.sh
# Fails loudly if a diagram cannot be rendered.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

node <<'EOF'
const [major, minor] = process.versions.node.split('.').map(Number);
if (major < 20 || (major === 20 && minor < 19)) {
  console.error(`FAIL render.sh requires Node.js 20.19+; found ${process.versions.node}.`);
  process.exit(1);
}
EOF

node --input-type=module <<'EOF'
import fs from 'node:fs';
import path from 'node:path';
import { JSDOM } from 'jsdom';

const mermaidModule = await import('mermaid');
const mermaid = mermaidModule.default ?? mermaidModule;

function installDomShims(window) {
  const globals = [
    'window',
    'document',
    'navigator',
    'Element',
    'HTMLElement',
    'SVGElement',
    'SVGGraphicsElement',
    'Node',
    'Text',
    'DOMParser',
    'XMLSerializer',
    'MutationObserver',
    'getComputedStyle',
    'CSSStyleSheet',
  ];

  for (const key of globals) {
    globalThis[key] = window[key];
  }

  globalThis.requestAnimationFrame = window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  globalThis.cancelAnimationFrame = window.cancelAnimationFrame = (id) => clearTimeout(id);

  const zeroTags = new Set(['style', 'defs', 'title', 'desc', 'metadata', 'clipPath', 'marker']);

  const measureText = (text) => {
    const lines = String(text || '').split(/\r?\n/);
    const widest = lines.reduce((max, line) => Math.max(max, line.length), 0);
    return { width: Math.max(1, widest * 8), height: Math.max(1, lines.length * 18) };
  };

  const bboxFor = (element) => {
    const tag = element.tagName ? element.tagName.toLowerCase() : '';
    if (zeroTags.has(tag)) {
      return { x: 0, y: 0, width: 0, height: 0 };
    }
    if (tag === 'rect' || tag === 'image' || tag === 'foreignobject') {
      const width = Number(element.getAttribute('width') || 0);
      const height = Number(element.getAttribute('height') || 0);
      return { x: 0, y: 0, width: width || 1, height: height || 1 };
    }
    if (tag === 'circle' || tag === 'ellipse') {
      const radius = Number(element.getAttribute('r') || Math.max(Number(element.getAttribute('rx') || 1), Number(element.getAttribute('ry') || 1)));
      return { x: 0, y: 0, width: radius * 2 || 1, height: radius * 2 || 1 };
    }
    if (tag === 'path' || tag === 'line' || tag === 'polyline' || tag === 'polygon') {
      return { x: 0, y: 0, width: 10, height: 10 };
    }
    if (tag === 'text' || tag === 'tspan') {
      return { x: 0, y: 0, ...measureText(element.textContent || '') };
    }
    if (tag === 'svg') {
      const width = Number(element.getAttribute('width') || 2600);
      const height = Number(element.getAttribute('height') || 1500);
      return { x: 0, y: 0, width: width || 1, height: height || 1 };
    }
    if (element.children && element.children.length > 0) {
      let maxWidth = 0;
      let maxHeight = 0;
      for (const child of element.children) {
        const box = typeof child.getBBox === 'function' ? child.getBBox() : bboxFor(child);
        maxWidth = Math.max(maxWidth, box.width || 0);
        maxHeight = Math.max(maxHeight, box.height || 0);
      }
      return { x: 0, y: 0, width: Math.max(maxWidth, 1), height: Math.max(maxHeight, 1) };
    }
    return { x: 0, y: 0, ...measureText(element.textContent || '') };
  };

  for (const proto of [window.SVGElement?.prototype, window.SVGGraphicsElement?.prototype]) {
    if (!proto) continue;
    proto.getBBox = function getBBox() {
      return bboxFor(this);
    };
    proto.getComputedTextLength = function getComputedTextLength() {
      return measureText(this.textContent || '').width;
    };
  }
}

function addWhiteBackground(svg) {
  const svgOpen = svg.indexOf('<svg');
  if (svgOpen === -1) return svg;
  const svgClose = svg.indexOf('>', svgOpen);
  if (svgClose === -1) return svg;
  const background = '<rect width="100%" height="100%" fill="white"/>';
  if (svg.slice(svgOpen, svgClose + 1).includes(background)) return svg;
  return svg.slice(0, svgClose + 1) + background + svg.slice(svgClose + 1);
}

installDomShims(new JSDOM('<!doctype html><html><body></body></html>', { pretendToBeVisual: true, runScripts: 'outside-only' }).window);
mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });

const mmdFiles = [...fs.readdirSync('.').filter((name) => name.endsWith('.mmd'))].sort();
for (const filename of mmdFiles) {
  const source = fs.readFileSync(filename, 'utf8');
  const svgFile = path.basename(filename, '.mmd') + '.svg';
  try {
    const { svg } = await mermaid.render(path.basename(filename, '.mmd'), source);
    let rendered = addWhiteBackground(svg);
    rendered = rendered.replace('@import url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css");', '');
    rendered = rendered.replace('display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;', 'display: table-cell; white-space: normal; line-height: 1.5; max-width: 200px; text-align: center;');
    fs.writeFileSync(svgFile, rendered);
    console.log(`OK  ${svgFile}`);
  } catch (error) {
    console.error(`FAIL ${filename}: ${error && error.message ? error.message : error}`);
    process.exit(1);
  }
}

console.log('Done.');
EOF
