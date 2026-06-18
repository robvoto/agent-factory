# Knowledge Flow — How Agents Learn and Share

All agents read from and write to one shared knowledge store. Knowledge compounds over time.

```mermaid
flowchart LR
    subgraph Sources["Knowledge Sources"]
        direction TB
        LocalDocs["Local docs/\narchitecture, contracts,\nworkflows, ADRs"]
        TrustedURLs["Trusted online sources\nLangChain, LangGraph,\nAnthropix, OpenAI docs"]
        AgentOutcomes["Agent outcomes\nwhat worked, what failed,\npatterns discovered"]
        UserPrefs["User preferences\ndecisions made,\nstyle choices"]
    end

    subgraph Store["Shared Knowledge Store\nknowledge_store.sqlite3"]
        direction TB
        SharedDocs["(shared, docs)\narchitecture + standards"]
        SharedTrusted["(shared, trusted)\nonline reference docs"]
        AgentLearnings["(agent, id, learnings)\nper-agent experience"]
        UserMemory["(user, id, preferences)\nper-user preferences"]
    end

    subgraph Agents["All Agents — Read + Write"]
        direction TB
        FactoryBrain["Factory Brain\nreads architecture\nwrites decisions"]
        ArmyOrch["Army Orchestrator\nreads routing patterns\nwrites routing outcomes"]
        ATL["AI Tech Lead\nreads coding patterns\nwrites task outcomes"]
        FutureAgents["Future agents\nadd as they join the army"]
        Keeper["Knowledge Keeper\nindexes + compacts\nruns on schedule"]
    end

    LocalDocs -->|ingested on change| SharedDocs
    TrustedURLs -->|crawled on schedule| SharedTrusted
    AgentOutcomes -->|written after each task| AgentLearnings
    UserPrefs -->|written during conversation| UserMemory

    SharedDocs <-->|search + write| FactoryBrain
    SharedTrusted <-->|search| FactoryBrain
    AgentLearnings <-->|search + write| FactoryBrain

    SharedDocs <-->|search| ArmyOrch
    AgentLearnings <-->|search + write| ArmyOrch

    SharedDocs <-->|search| ATL
    SharedTrusted <-->|search| ATL
    AgentLearnings <-->|write| ATL

    AgentLearnings <-->|write| FutureAgents

    Keeper -->|re-index, deduplicate, compact| Store

    style Store fill:#e8f4e8,stroke:#5a9e5a
    style Keeper fill:#fff3e0,stroke:#e6a817
```

## How knowledge moves

1. **Indexing** — Knowledge Keeper reads `docs/` and trusted URLs, writes chunks to `(shared, docs)` and `(shared, trusted)` namespaces
2. **Retrieval** — Every agent calls `search_memory` and `search_trusted_sources` tools at the start of relevant tasks
3. **Writing** — Every agent calls `manage_memory` after decisions, task completions, and discoveries
4. **Compaction** — Knowledge Keeper runs periodic deduplication so the store doesn't grow forever

## What is NOT shared

- **Conversation checkpoints** — each agent's thread history stays in its own SQLite file
- **Backlogs** — each agent manages its own work queue
- **Secrets** — API keys, tokens — never touch the knowledge store
