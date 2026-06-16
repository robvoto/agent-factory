# Coding Task — End to End

A full coding task from your message to changed files, through every layer.

```mermaid
flowchart TD
    You([👤 You])

    subgraph Entry["Entry Points — pick one"]
        ArmyTG["Army Bot\n'fix the login bug'"]
        ATLTGDirect["AI Tech Lead Bot\n'/run JH-042'"]
    end

    subgraph ArmyLayer["Army Layer"]
        ArmyOrch["Orchestrator LLM\ndetects coding intent"]
        SubProc["Subprocess call\nrun-agent-task input.json"]
    end

    subgraph ATLWorkflow["AI Tech Lead Workflow (LangGraph)"]
        ReadReq["1. Read request\nvalidate + normalise"]
        Research["2. Check research\nneed local docs?"]
        Risk["3. Review risk\nscope, permissions, danger"]
        Clarify["4. Check clarification\nis task unambiguous?"]
        Analyse["5. Tech lead analysis\nformulate bounded task\nbuild brief"]
        Approval["6. Approval gate\nneeds_approval check"]
        Instruction["7. Build instruction\nbounded, safe prompt\nfor coding backend"]
        RunAgent["8. Run coding agent\nCodex / Claude Code\n(if execution approved)"]
        End["9. Return result\nchanged files, evidence, logs"]
    end

    subgraph HumanGates["Human-in-the-Loop Gates"]
        ClarifyQ["❓ Ask clarification\nvia Telegram"]
        ApproveQ["⚠️ Request approval\nvia Telegram"]
        FailQ["🚨 Failure interrupt\ntoo risky to retry"]
    end

    subgraph Output["Output"]
        JSONOut["output.json\nstatus, instruction,\nresult, evidence"]
        TGResponse["Telegram response\nsummary to you"]
        ChangedFiles["Changed files\nin target project"]
    end

    You --> ArmyTG
    You --> ATLTGDirect

    ArmyTG --> ArmyOrch
    ArmyOrch --> SubProc
    SubProc --> ReadReq
    ATLTGDirect --> ReadReq

    ReadReq --> Research
    Research --> Risk
    Risk --> Clarify

    Clarify -->|ambiguous| ClarifyQ
    ClarifyQ -->|your answer| Clarify

    Clarify -->|clear| Analyse
    Analyse --> Approval

    Approval -->|risky| ApproveQ
    ApproveQ -->|/approve| Instruction
    ApproveQ -->|/reject| End

    Approval -->|safe| Instruction
    Instruction --> RunAgent

    RunAgent -->|success| End
    RunAgent -->|failure| FailQ
    FailQ -->|retry| RunAgent
    FailQ -->|too many retries| End

    End --> JSONOut
    JSONOut --> TGResponse
    JSONOut --> ChangedFiles
    TGResponse --> You

    style ClarifyQ fill:#fff3e0,stroke:#e6a817
    style ApproveQ fill:#fce8e8,stroke:#cc4444
    style FailQ fill:#fce8e8,stroke:#cc4444
    style ChangedFiles fill:#d4edda,stroke:#28a745
```

## What each step does

| Step | Purpose | Can pause? |
|---|---|---|
| Read request | Validate task is not empty | No |
| Check research | Does this task need LangChain docs? | Yes — asks if online fetch needed |
| Review risk | Scope creep? Dangerous operations? | No — flags but continues |
| Check clarification | Is the task specific enough to act on? | Yes — asks you |
| Tech lead analysis | Formulates the bounded task + brief | No |
| Approval gate | Should a human approve before execution? | Yes — /approve or /reject |
| Build instruction | Creates the prompt for the coding backend | No |
| Run coding agent | Calls Codex/Claude Code with the instruction | Yes — on failure |
