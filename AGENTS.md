# AGENTS.md

See [CONTRIBUTING.md](./CONTRIBUTING.md) for all project guidelines.

## Agent tooling

- Follow TigerStyle priorities: Safety → Performance → Developer Experience.
- For code exploration and edits, use [token-efficient-coding](.agents/skills/token-efficient-coding/SKILL.md).
- Use `rg` for exact text, Serena MCP for symbols and references, and `grepai` CLI for semantic search.
  If an optional tool is unavailable, continue with `rg` and bounded file reads.
- Read [agent tooling](docs/agent-tools.md) only for setup, indexing, memory or architecture audits.
