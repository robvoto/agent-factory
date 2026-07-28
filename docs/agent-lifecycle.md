# Agent Lifecycle

## Goal

Agents should become runnable and improvable, but not uncontrolled.

The lifecycle is:

```text
Create → Validate → Approve → Run → Observe → Improve → Test → Promote
```

## 1. Create

A user describes the agent they want.

The Factory creates a staged draft, not a live agent.
For the draft-to-package flow, see `agent-creator-workflow.md`.

## 2. Validate

The platform validates:

- required fields
- duplicate aliases
- unknown tools
- permission shape
- memory policy
- runtime contract

Invalid agents fail closed.

## 3. Approve

Human approval is required before an agent becomes enabled.

Approval is especially important for:

- filesystem access
- network access
- shell commands
- external APIs
- long-running behaviour
- memory retention
- higher cost limits

## 4. Run

The Runtime runs only approved agents.

It should track:

- input
- output
- status
- errors
- logs
- token usage
- cost
- stop reason

## 5. Observe

Failures and user feedback become improvement evidence.

Do not hide failures behind retries.

## 6. Improve

The Improver proposes changes from evidence.

It may propose:

- bounded code changes;
- a new reusable skill;
- an update to an existing skill;
- `AGENTS.md` or other instruction changes;
- prompt, tool, permission, test, or documentation changes.

Each proposal must identify the evidence, problem, trigger condition, exact target,
bounded scope, risks, expected reusable benefit, validation, and rollback approach.

It must not silently apply or activate any self-change. Human approval is required
before implementation. Approved code changes use the normal coding workflow and
tests. Approved skills are registered in the relevant skill index and validated
before reuse. Agent Factory owns the canonical templates and upgrade path; Agent
Hub may route proposals but cannot bypass Factory governance.

## 7. Test

Every change needs validation evidence before promotion.

At minimum:

```bash
python -m pytest -q
```

Additional agent-specific tests can be added later.

## 8. Promote

Promotion means the new agent version becomes the active approved version.

Promotion requires:

- successful validation
- clear summary of changes
- approval when permissions, runtime behaviour, or cost changes

## Non-goals

Do not build:

- autonomous self-modifying agents
- hidden background loops
- uncontrolled discovery
- giant prompt files
- separate apps for create/run/improve
