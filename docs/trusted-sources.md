# Trusted Sources

Use these as the baseline when improving agent instructions, routing behavior, or prompt structure.

## 1. OpenAI Prompt Engineering

- URL: https://developers.openai.com/api/docs/guides/prompt-engineering
- Why it is trusted: official, current OpenAI documentation for prompt design and agentic coding workflows.
- Use it for:
  - precise role and workflow guidance
  - structured tool use with examples
  - testing and validation expectations
  - clean Markdown and output formatting
  - agentic task planning and persistence

## 2. Anthropic Prompting Best Practices

- URL: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- Why it is trusted: official, current Anthropic documentation for prompt engineering with latest Claude models.
- Use it for:
  - clear, direct instructions
  - examples and few-shot patterns
  - XML-style structure for mixed instructions and data
  - role prompting
  - thinking and agentic systems guidance

## 3. OpenAI Codex AGENTS.md Guide

- URL: https://developers.openai.com/codex/guides/agents-md
- Why it is trusted: official guidance for how Codex discovers and layers `AGENTS.md` files.
- Use it for:
  - root vs nested instruction scope
  - override precedence and fallback filenames
  - concise examples for layered repo instructions
  - verification commands and troubleshooting

## 4. LangChain Deep Agents Skills

- URL: https://docs.langchain.com/oss/python/deepagents/skills
- Why it is trusted: official guidance for packaging reusable agent behavior as skills.
- Use it for:
  - skill file structure and when to split behavior out of prompts
  - reusable workflow design
  - keeping detailed procedures out of always-loaded memory
  - examples for skills-first organization

## 5. LangChain Deep Agents Overview

- URL: https://docs.langchain.com/oss/python/deepagents/overview
- Why it is trusted: official overview of the agent lifecycle, subagents, memory, and human-in-the-loop patterns.
- Use it for:
  - agent lifecycle design
  - subagent boundaries
  - memory vs skill separation
  - approval and checkpointing patterns

## 6. Thoughtworks Technology Radar

- URL: https://www.thoughtworks.com/en-au/radar
- Why it is trusted: curated industry guidance from Thoughtworks that highlights current tools, techniques, platforms, languages, and frameworks to explore, with explicit Adopt / Trial / Assess / Caution rings.
- Use it for:
  - current engineering patterns and anti-patterns
  - evaluating emerging practices before adoption
  - balancing innovation with delivery risk
  - prioritizing practices that are current, practical, and widely field-tested

## Rule

- Do not invent behavior that is not grounded in these sources.
- Keep instruction files short, explicit, and fail-closed.
- Avoid hardcoded task-specific work unless a trusted source or repository contract makes it a best-practice requirement.
- Prefer negative constraints and deterministic rules over vague aspirational guidance.
