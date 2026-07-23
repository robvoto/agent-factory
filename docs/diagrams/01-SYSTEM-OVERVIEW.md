# System Overview — The Full Agent Platform

All components and how they connect. Every box is a real running process or data store.

```mermaid
flowchart TD
    subgraph You["👤 You"]
        direction LR
        Phone[Telegram app]
        Browser[Browser / VS Code]
    end

    subgraph Hub["agent-hub — Orchestrator"]
        HubBot[Agent Hub Telegram Bot]
        HubOrch[Orchestrator\ncreate_react_agent]
        HubReg[Agent Registry\nreads config/agents/]
    end

    subgraph Factory["agent-factory — Control Plane"]
        FactoryBot[Factory Brain Bot\nTelegram]
        FactoryBrain[Factory Brain\ndeep agent]
        AdminUI[Admin UI\nFastAPI]
        Staging[staging/agents/]
        Registry[config/agents/\nenabled registry]
        Approval[(Approvals\nSQLite)]
    end

    subgraph ATL["ai-tech-lead — Coding Specialist"]
        ATLBot[AI Tech Lead Bot\nTelegram]
        ATLGraph[Coding Workflow\nLangGraph]
        ATLBacklog[(Backlog\nSQLite)]
    end

    subgraph Jobs["job-hunter-agent — Job Specialist"]
        JobBot[Job Hunter Bot\nTelegram]
        JobGraph[Job Workflow]
    end

    subgraph Shared["Shared Infrastructure"]
        KnowledgeDB[(Knowledge Store\nSQLite — shared)]
        CheckpointDB[(Checkpoints\nper-project SQLite)]
        CodingBackend[Coding Backend\nCodex / Claude Code]
    end

    Phone -->|any task| HubBot
    Phone -->|factory commands| FactoryBot
    Phone -->|coding tasks| ATLBot
    Phone -->|job tasks| JobBot
    Browser --> AdminUI

    HubBot --> HubOrch
    HubOrch --> HubReg
    HubReg --> Registry

    HubOrch -->|coding task\nJSON subprocess| ATLGraph
    HubOrch -->|job task\nJSON subprocess| JobGraph
    HubOrch -->|design agent\nJSON subprocess| FactoryBrain

    FactoryBot --> FactoryBrain
    FactoryBrain --> Staging
    FactoryBrain --> Approval
    Staging -->|approved + promoted| Registry
    AdminUI --> Registry

    ATLBot --> ATLGraph
    ATLGraph --> CodingBackend
    ATLGraph --> ATLBacklog

    JobBot --> JobGraph

    FactoryBrain <-->|read/write| KnowledgeDB
    HubOrch <-->|read/write| KnowledgeDB
    ATLGraph <-->|read/write| KnowledgeDB
    JobGraph <-->|read/write| KnowledgeDB

    FactoryBrain --- CheckpointDB
    ATLGraph --- CheckpointDB
    HubOrch --- CheckpointDB

    style KnowledgeDB fill:#e8f4e8,stroke:#5a9e5a
    style CheckpointDB fill:#fff3e0,stroke:#e6a817
    style Registry fill:#dbeafe,stroke:#3b82f6
    style Approval fill:#fce8e8,stroke:#cc4444
    style CodingBackend fill:#f3e8ff,stroke:#7c3aed
```

## Key rules

- **Factory** designs and promotes agents. It never runs coding work itself.
- **Orchestrator** routes requests. It never performs the work itself.
- **Specialist agents** (ai-tech-lead, job-hunter) do the actual work. They exist independently of the hub.
- **Knowledge Store** is shared. One SQLite file, all agents read from and write to it.
- **Checkpoints** are per-project. Each agent's conversation history stays in its own file.
- Every agent can also be used directly via its own Telegram bot — the hub is an additional entry point, not a replacement.
