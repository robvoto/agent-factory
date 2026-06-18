# Army Routing — Interaction Diagram

This is the interaction diagram for how a request reaches the right agent.
The orchestrator receives every request and decides which agent handles it.
You never route manually unless you want to.

```mermaid
sequenceDiagram
    actor You
    participant Bot as Army Telegram Bot
    participant Orch as Orchestrator LLM<br/>(create_react_agent)
    participant Reg as Agent Registry<br/>(config/agents/)
    participant ATL as AI Tech Lead<br/>subprocess
    participant Job as Job Hunter<br/>subprocess
    participant FB as Factory Brain<br/>subprocess
    participant KB as Knowledge Store

    You->>Bot: "Find me senior Python roles in Melbourne"
    Bot->>Orch: forward message

    Orch->>KB: search_memory("job search Python Melbourne")
    KB-->>Orch: relevant past searches + patterns

    Orch->>Reg: list available agents
    Reg-->>Orch: [ai-tech-lead, job-hunter, ...]

    Orch->>Orch: LLM decides: this is a job task → job-hunter

    Orch->>Job: run-agent-task input.json
    Note over Job: runs job search workflow
    Job-->>Orch: output.json {status: success, results: [...]}

    Orch->>KB: manage_memory("routing: job search → job-hunter, success")
    Orch-->>Bot: formatted response
    Bot-->>You: "Found 12 roles. Top match: ..."

    Note over You, KB: --- Different request ---

    You->>Bot: "Fix the null pointer bug in job-hunter"
    Bot->>Orch: forward message

    Orch->>Orch: LLM decides: this is a coding task → ai-tech-lead

    Orch->>ATL: run-agent-task input.json\n{project_root: job-hunter-agent,\ntask: "fix null pointer bug"}

    alt Needs clarification
        ATL-->>Orch: {status: needs_clarification,\nnext_action: "Which null pointer?"}
        Orch-->>Bot: relay question
        Bot-->>You: "Which null pointer bug? In the search loop or the result parser?"
        You->>Bot: "The result parser"
        Orch->>ATL: run-agent-task (updated input with clarification)
    end

    ATL-->>Orch: {status: success,\ncoding_agent_instruction: "...",\nformulated_task: "..."}
    Orch-->>Bot: "AI Tech Lead has analysed the bug and prepared instructions."
    Bot-->>You: summary + instruction
```

## How the LLM decides which agent to call

Each enabled agent in `config/agents/` becomes a tool in the orchestrator's tool list:

```
Tool: ai-tech-lead
Description: "AI Tech Lead: Handles coding task clarification, risk review,
              planning, and instruction generation for coding backends."

Tool: job-hunter  
Description: "Job Hunter: Finds job listings matching skills and location."
```

The orchestrator LLM reads your message and picks the right tool. If no agent fits, it answers directly or says what's missing.
