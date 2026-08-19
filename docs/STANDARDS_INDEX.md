# Project Standards Index

Rob's project standards source of truth is the Google Drive standards folder:

https://drive.google.com/drive/u/1/folders/14-mkDcSsRd78yTIT17mK03jGPjcGRRNS

This file is only a local pointer. Do not copy the full standards into this repo unless explicitly requested.

## How agents should use this

- Start from `docs/INDEX.md` for local project documentation.
- Use this file when the task touches shared standards, project setup, documentation structure, logging, cost tracking, backlog process, automation, CI/CD, deployment, AGENTS.md, or skills.
- Check the Google Drive standards folder before changing those areas.
- If Google Drive cannot be accessed, stop and ask the operator for the current exported standards text.
- Do not guess standards updates.

## Mandatory standards already confirmed for this project

- README stays short: purpose, repo role, canonical path, and where to start.
- `docs/INDEX.md` is the single documentation entry point.
- Detailed commands belong in a specific commands document, not README.
- Backlog source of truth is the live Google Sheet; do not create duplicate local backlog files.
- Use friendly normal logs and detailed debug logs.
- Exceptions must be obvious; do not hide failures with silent fallbacks.
- Fallbacks, compatibility shims, hardcoded replacements, and silent defaults require explicit approval.
- Every LLM call should log model, purpose, token usage when available, cost when available, and stop reason.
- Enforce cost/token budgets and stop before expensive or uncertain work.
- Persistent data belongs under `data/`; documentation belongs under `docs/`.
