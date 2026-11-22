# AGENTS.md

See [CONTRIBUTING.md](./CONTRIBUTING.md) for all project guidelines.

## Agent tooling

- Follow TigerStyle priorities: Safety → Performance → Developer Experience.
- For code exploration and edits, use [token-efficient-coding](.agents/skills/token-efficient-coding/SKILL.md).
- Use `rg` for exact text, Serena MCP for symbols and references, and `grepai` CLI for semantic search.
  If an optional tool is unavailable, continue with `rg` and bounded file reads.
- Read [agent tooling](docs/agent-tools.md) only for setup, indexing, memory or architecture audits.

## Cytiq wiki

When a change affects features, public contracts, compatibility, setup, deployment, or operations, update the
relevant pages in [cytiq-wiki](https://github.com/cytiq/cytiq-wiki) as part of the same change. Document affected
version pins, migrations, and verification steps where applicable. Update the repository index and navigation
when adding a repository or guide.
