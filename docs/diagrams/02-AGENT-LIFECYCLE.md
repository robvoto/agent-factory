# Agent Lifecycle — From Idea to Army

How an agent goes from an idea to a running specialist in the army.

```mermaid
stateDiagram-v2
    [*] --> Idea : You describe a need

    Idea --> Designing : Factory Brain starts designing
    Designing --> Staged : Factory Brain produces\nagent package\n(agent.json, SYSTEM.md,\npermissions.json, tools.json)

    Staged --> UnderReview : You review the draft\nvia Telegram or Admin UI
    UnderReview --> Rejected : /reject — back to designing
    UnderReview --> Approved : /approve

    Rejected --> Designing : Factory Brain refines

    Approved --> Enabled : Promoted to config/agents/\nArmy registry picks it up

    Enabled --> Running : Army Orchestrator\nroutes tasks to it

    Running --> Learning : Agent writes outcomes\nto shared knowledge store

    Learning --> Running : Next task benefits\nfrom past learning

    Running --> Improving : Factory Brain reads\nagent outcomes,\npropose v2 spec

    Improving --> Staged : New version staged\nOld version archived on approval

    Running --> Retired : /delete or superseded by v2

    Retired --> [*]
```

## What happens at each stage

| Stage | Who acts | Where it lives |
|---|---|---|
| Idea → Designing | You + Factory Brain | Conversation in Telegram |
| Staged | Factory Brain | `staging/agents/<id>/` |
| Under Review | You | Admin UI or Telegram `/staged` |
| Enabled | Factory (on `/approve`) | `config/agents/<id>/agent.json` |
| Running | Army Orchestrator | Live, called via subprocess |
| Learning | The agent itself | `knowledge_store.sqlite3` |
| Improving | Factory Brain (reads logs) | New staging draft |
