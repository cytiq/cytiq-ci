# Agent tooling

Load this guide for setup or troubleshooting. Shared instructions live in `AGENTS.md`,
project conventions in `CONTRIBUTING.md` (or `AGENTS.md` when absent), and the exploration workflow in
[token-efficient-coding](../.agents/skills/token-efficient-coding/SKILL.md).

## Integration

- **Codex:** `.codex/config.toml` adds only Serena, using the `codex` context. Project configuration
  requires a trusted project; restart the client after changing MCP configuration and inspect `/mcp`.
  CLI launches detect the project from the working directory. If the desktop client starts elsewhere,
  ask Serena to activate this checkout by its absolute path before using symbols.
- **Claude Code:** `.mcp.json` starts Serena in the `claude-code` context with `${CLAUDE_PROJECT_DIR}`.
  Review the repository MCP configuration when the client prompts, then inspect `/mcp`.
  `CLAUDE.md` imports `AGENTS.md`; its Skill directory links to the shared `.agents/skills/` entry.
- **grepai:** CLI only for both clients. Do not also add `grepai mcp-serve` or run `agent-setup` here.
  Existing unrelated user MCP servers and Skills are preserved.

Serena uses the official `serena-agent==2.1.0` package through `uvx --python 3.13`;
the first client launch may download dependencies into uv's normal cache. Python 3.13 runs Serena
independently of the interpreter pinned by this project. Update the version in both client launchers together.
No global install is required. If an explicit installation is preferred and `serena` is absent:

```sh
uv tool install --python 3.13 serena-agent==2.1.0
```

Both launchers select Serena's compact `REPL` interface: symbol and editing APIs are discovered on demand.
Claude exposes two entrypoints (`initial_instructions`, `serena_repl`); Codex also exposes project activation.

Optional missing CLI installation commands (run only for tools absent from `PATH`):

```sh
brew install yoanbernabeu/tap/grepai ollama uv ripgrep
```

## Navigation and indexing

Use `rg` for a known name or configuration key, Serena for symbols and references,
and grepai when the relevant identifier is unknown. Serena enables python in this repository;
YAML configuration and documentation remain searchable with grepai and `rg`. Index only this checkout.

Serena reads `.serena/project.yml`; `project.local.yml` supports optional local overrides and is ignored.
Use the existing project configuration on subsequent runs instead of recreating it:

```sh
uvx --python 3.13 --from serena-agent==2.1.0 serena project index
uvx --python 3.13 --from serena-agent==2.1.0 serena project health-check
```

In the client, obtain the session ID with `initial_instructions` if it was not supplied on connection.
Use `serena_repl` to request `s.info("lsp")` as needed, then
`s.lsp.get_symbols_overview("path/to/source", depth=0)`. Use `s.lsp.find_symbol` for the selected
definition and `s.lsp.find_referencing_symbols` for callers; fetch bodies only after locating the symbol.

grepai embeds only through the loopback Ollama endpoint and stores vectors in `.grepai/index.gob`.
If Ollama is stopped, start the installed app or run `ollama serve` in a separate terminal.
If the model is missing, download it once with `ollama pull nomic-embed-text`.

```sh
grepai watch --status
grepai index
grepai search "project configuration and validation" --limit 5 --json --compact
grepai search "input validation and error handling" --limit 3 --json --compact
grepai status --no-ui
```

`grepai index` refreshes once, skips unchanged files, and exits. `watch.discover_worktrees: false`
disables linked-worktree discovery; ignore rules also exclude nested temporary worktrees and caches.
Source files, configuration and tests remain included. Preserve `.grepai/config.yaml` and the existing index;
do not rerun `grepai init` or change embedding dimensions on repeat setup.
grepai may expand defaults and update `watch.last_index_time` in its configuration during indexing;
these runtime metadata changes do not require reinitialization or an index reset.
Only start `grepai watch` for a sustained need for live updates, after checking that no watcher
already serves this checkout. Do not add watchers to CI or start them for temporary worktrees.

## Architecture context on request

Repomix is optional and runs locally. If absent, use `npx --yes repomix` instead of a global install.
Select architecture-relevant source paths, honor `.gitignore`, keep secret scanning enabled,
and write output under ignored `.serena/`. Run only when an architecture audit needs a broader view:

```sh
npx --yes repomix --compress --token-count-tree --output .serena/repomix-output.xml
```

Inspect the token-count tree and load only the relevant parts. Do not generate a dump on startup,
commit the output, or send it to an external service as part of indexing.

## Memory and repeat setup

Reuse native agent session summaries or existing Serena memories under `.serena/memories/`.
Keep only short decisions and path references; no source copies or secrets. Memories, indexes and logs
are local and ignored. No separate memory service or repository-level prompt caching implementation is needed.
Stable short entrypoints and on-demand Skills keep the baseline context small.

On repeat setup, inspect the current configuration, preserve user overrides and existing indexes,
refresh indexes only if needed, and reuse the shared Skill link. No reset, worktree creation or cleanup is needed.
Check `git diff --check` and `git status --short --untracked-files=all` before committing;
only the two indexer configuration files should be visible inside `.serena/` and `.grepai/`.

## Sources

- [Serena installation](https://oraios.github.io/serena/02-usage/010_installation.html),
  [project workflow](https://oraios.github.io/serena/02-usage/040_workflow.html)
- [Codex MCP configuration](https://developers.openai.com/codex/mcp)
- [Claude Code Skills and symlinks](https://code.claude.com/docs/en/skills)
- [grepai configuration](https://yoanbernabeu.github.io/grepai/configuration/),
  [worktree discovery](https://yoanbernabeu.github.io/grepai/watch-guide/)
- [Repomix configuration](https://repomix.com/guide/configuration)
