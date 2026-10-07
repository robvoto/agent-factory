# Agent Lifecycle

## Goal

Agents should become runnable and improvable, but not uncontrolled.

The lifecycle is:

```text
Create → Validate → Approve → Run → Observe → Improve → Test → Promote
```

## Lifecycle levels and ownership

The lifecycle has three levels. Promotion and graduation are different decisions.

The default path is approval, promotion to a standard release, and enablement. Most
agents stop at that level. Only a concrete proposal that an agent has genuine
independent engineering needs enters an optional graduation review. If the proposal is
rejected or not justified, the agent remains a standard released agent.

| Level | Meaning and home | Hub visibility | Owner and change authority |
|---|---|---|---|
| Prototype / incubating | An unapproved design or package in `staging/agents/<id>/` | Not Hub-callable | Factory owns the package and may redesign or rebuild it within the approved task. |
| Standard released agent | A validated package promoted into the enabled registry; it may remain entirely Factory-owned | Runnable through the enabled registry after approval and promotion | Factory owns the package, manifest, release contract, permissions, promotion, activation metadata, and governed upgrades. A new release still goes through staging, validation, approval, and promotion. |
| Independent product agent | A product with genuine independent engineering needs, implemented in its own specialist repository after an explicit decision | Runnable only through its Factory-governed released definition | The specialist repository owns implementation, dependencies, product tests, and its implementation release work. Factory continues to gate registration, the release contract, permissions, promotion, activation metadata, and governed upgrades. |

Graduation to an independent product repository is an explicit human and architecture
decision. It is appropriate only when the agent has needs such as substantial custom
code, its own dependencies, a database or schema, provider integrations, deployment or
runtime concerns, independent CI/testing, or a separate release cadence. It is not an
automatic threshold or heuristic. Simple agents must not be split into separate
repositories, and complex product agents must not be trapped in Factory staging.

Shopping Agent may remain Factory-owned as a standard released agent initially. It
graduates only if its engineering needs later justify the explicit decision; this
decision does not require Shopping-specific runtime logic in Factory.

## Release, modification, and Hub boundaries

Factory owns the lifecycle gate for both Factory-owned standard agents and independent
product agents. A release is not active merely because implementation files exist:
Factory validation and explicit human approval are required before activation when a
change affects permissions, tools or capability declarations, the runtime contract,
manifest-governed model or cost limits, or the active release version.

Factory may manufacture or propose upgrades, but it must not silently self-modify a
released independent product agent. Its specialist repository remains the implementation
owner after graduation. Agent Hub consumes released definitions from the enabled
registry and runs or orchestrates them; it does not use staged packages, modify the
registry directly, become the development home, or decide that an agent should graduate.

Release rollback belongs to release governance: activate a previously validated release
or version through the normal Factory-controlled registry path. Do not restore arbitrary
filesystem snapshots or copy random old files. Factory Brain checkpoint rollback, where
documented, is a conversation-state operation and is not a release rollback.

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
before reuse. Agent Factory owns the canonical templates, release governance, and
upgrade path; Agent Hub may route proposals but cannot bypass Factory governance.

## 7. Test

Every change needs validation evidence before promotion.

At minimum:

```bash
python -m pytest -q
```

Additional agent-specific tests can be added later.

## 8. Promote

Promotion is the Factory-controlled release step that makes a validated version the
active approved registry version. For a standard released agent, promotion does not
graduate it to another repository. For an independent product agent, promotion activates
the released definition supplied by its specialist repository; it does not transfer
implementation ownership to Factory or Hub.

Promotion requires:

- successful validation
- clear summary of changes
- explicit human approval before activation when permissions, tools or capability
  declarations, runtime contract, manifest-governed model or cost limits, or the active
  release version changes

## Non-goals

Do not build:

- autonomous self-modifying agents
- hidden background loops
- uncontrolled discovery
- giant prompt files
- separate apps for create/run/improve
