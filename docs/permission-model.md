# Permission Model

Default rule: fail closed.

- A manifest may only name tools listed in `config/tools.json`.
- Unknown tools are rejected during manifest loading.
- MCP server/tool declarations are rejected at the runtime loading boundary unless they are present in the explicit `config/mcp_servers.json` approval registry and within its permission boundary.
- Runtime MCP loading requires an explicit availability/handle map; Factory performs no implicit server discovery.
- Unavailable or denied MCP declarations fail closed with an error.
- Unknown aliases are rejected during routing.
- Missing agents are not routed elsewhere.
- `permissions` and `memory` are required objects.

This scaffold validates references and selects authorized MCP handles. It does not execute tools or provide an MCP transport.
