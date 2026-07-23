# Hub progress adapter

This package was explicitly configured for live Hub progress.

- stdout is reserved for versioned `SpecialistProgressEvent` JSONL when both `run_id` and `request_id` are supplied
- normal and debug logs stay on stderr
- the final result stays in the existing output JSON file
- deterministic workflows call `ProgressReporter.phase(...)` directly
- simple agents translate bounded callback events with `handle_simple_agent_event(...)`
- Deep Agents translate streamed structure with `handle_deep_agent_event(...)` or `run_agent_with_progress(...)`

Never emit prompts, hidden reasoning, raw model/provider payloads, secrets, or unbounded logs.
