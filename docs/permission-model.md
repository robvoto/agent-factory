# Permission Model

Default rule: fail closed.

- A manifest may only name tools listed in `config/tools.json`.
- Unknown tools are rejected during manifest loading.
- Unknown aliases are rejected during routing.
- Missing agents are not routed elsewhere.
- `permissions` and `memory` are required objects.

This scaffold validates references. It does not execute tools.
