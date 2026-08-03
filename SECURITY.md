# Security Policy

## Sensitive material

Agent Factory may handle provider credentials, Telegram credentials, generated agent specifications, approval state, registry configuration, and lifecycle databases. Do not commit or publish:

- API keys, bot tokens, cookies, passwords, or webhook secrets;
- local `.env` files or credential stores;
- generated runtime databases or operator-specific configuration;
- private project material copied into agent prompts or templates;
- approval tokens or internal connector credentials.

## Generated agent packages

Treat every generated or edited agent package as untrusted until it has passed validation and human review.

- Validate the manifest and interaction contract.
- Validate tool and filesystem permissions explicitly.
- Reject undeclared network, command, repository, or memory access.
- Do not place secrets in manifests, templates, prompts, or default configuration.
- Keep unapproved packages in `staging/agents/`.
- Promote packages only through the approval workflow.

## Factory tools

Factory tools must remain bounded to the intended staging and registry paths. They must not dispatch user work, modify unrelated projects, or silently enable an agent.

## LLM-assisted creation

LLM output is draft material, not an approval decision. Generated specifications may contain unsafe, excessive, or inconsistent permissions and must be validated before staging or promotion.

## Telegram administration

- Store the bot token outside source control.
- Restrict the administration bot to approved users or chats.
- Do not send secrets, private source files, or full sensitive logs through chat.
- Apply the same approval rules regardless of whether a request arrives through CLI or Telegram.

## Reporting

Report suspected vulnerabilities privately to the repository owner. Provide a minimal sanitised reproduction and do not attach credentials, private agent registries, or lifecycle databases to an issue.
