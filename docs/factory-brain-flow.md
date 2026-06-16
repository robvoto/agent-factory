# Factory Brain Flow

Current as of 2026-06-15. This Markdown/Mermaid version is the current source view. The old standalone PNG preview has been moved to `diagrams/_review-old-pngs/` for review and is not part of the current canonical diagram set yet.

```mermaid
flowchart TD
    Start([Start / new message]) --> Skills[Load Skills from skills/]
    Skills --> Memory[Inject AGENTS.md\nstatic rules only]
    Memory --> LLM[Factory Brain LLM]

    LLM --> Decide{Call a tool?}

    Decide -->|yes| WhichTool{Which tool?}
    Decide -->|no| Respond([Respond to user\nmay be answer, question,\nor clarification request])

    WhichTool -->|safe tools| SafeTools["list_staged_agents\nread_staged_review\nlist_templates\nrecord_decision"]
    WhichTool -->|memory tools| MemTools["manage_memory — write learnings\nsearch_memory — search local docs\nsearch_trusted_sources — search online"]
    WhichTool -->|approval-required| ApprovalTool["request_approval\nrequest_agent_promotion"]

    SafeTools --> RunTool[Run Tool]
    MemTools --> KnowledgeStore[(Knowledge Store\nSQLite — shared\nacross all agents)]
    KnowledgeStore --> RunTool
    RunTool --> LLM

    ApprovalTool --> Checkpoint[(Checkpoint saved\nto SQLite)]
    Checkpoint --> Interrupt[INTERRUPT\nwait for human]
    Interrupt --> Human{Human\n/approve or /reject?}
    Human -->|/approve| Resume[Resume thread\nfrom checkpoint]
    Human -->|/reject| Reject[Inject rejection\nvia update_state]
    Resume --> LLM
    Reject --> LLM

    style KnowledgeStore fill:#e8f4e8,stroke:#5a9e5a
    style Checkpoint fill:#fff3e0,stroke:#e6a817
    style Interrupt fill:#fff3e0,stroke:#e6a817
    style Human fill:#fce8e8,stroke:#cc4444
    style Respond fill:#d4edda,stroke:#28a745
```

## What each layer does

| Layer | What | Token cost |
|---|---|---|
| Skills | Loaded on-demand per task type | Pay only when skill matches |
| AGENTS.md | Static rules, always injected | Fixed small cost per turn |
| Knowledge Store | Retrieved on-demand via search tools | Pay only for top-K relevant chunks |
| Checkpoints | Every turn saved to SQLite | Zero token cost — storage only |
| manage_memory | Writes learnings to store | One tool call per learning |

## Not yet implemented (in roadmap)

- `/checkpoints` — list past states for the current thread
- `/rollback <id>` — restore thread to a past checkpoint
- `/fork <id>` — branch a new thread from a past checkpoint
- Hot reload — code changes without restarting the gateway
- Semantic search — current store uses keyword matching, not embeddings
