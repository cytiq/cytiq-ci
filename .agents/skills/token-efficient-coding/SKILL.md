---
name: token-efficient-coding
description: Minimize context during code exploration, editing and validation using exact search, symbols and bounded reads.
---

# Token-efficient coding

Apply Safety → Performance → Developer Experience; preserve project conventions and unrelated changes.

1. **Search before read.** Locate candidates with scoped `rg --files -g 'pattern'` before opening them.
2. **Symbol before file.** This repository uses Serena's compact REPL interface. Obtain its session ID from
   `initial_instructions` once if not already supplied, then use `serena_repl` and load `s.info("lsp")` as needed.
   Start with `s.lsp.find_symbol` or `s.lsp.get_symbols_overview` without bodies; fetch only the chosen definition,
   use `s.lsp.find_referencing_symbols` for impact, then use the relevant editing facade for a targeted edit.
   With a tools-based Serena connection, use the corresponding symbol tools directly.
3. **Exact before semantic.** For a known identifier use `rg -n -F -m 5 'identifier' path/to/candidates`.
   For unknown names use `grepai search "English description" --limit 5 --json --compact`;
   narrow with `--path` when useful. Use grepai through CLI here, without a duplicate MCP integration.
4. **Minimal context.** Load only the definition, relevant callers, types and tests needed for the change.
   For YAML and other configuration, locate a key with `rg` and read its enclosing block.
5. **Bounded output.** Scope paths and result counts; use `sed -n 'START,ENDp' file` for a selected range.
   `rg -m` limits matches per file, so also bound the candidate files. Avoid repository dumps and truncated logs.
6. **No redundant reads.** Reuse established findings; reread only when the file changed or a new dependency matters.
7. **Targeted validation.** Run the affected test or check first, then required project gates as appropriate.
   Do not run autoformatting across unrelated changes.
8. **Context reuse.** Reuse native session summaries or existing Serena memories. When a durable finding helps,
   save a few bullets with paths, decisions and validation commands; no source copies, transcripts or secrets.
   Confirm an old finding against current code before relying on it.
9. **Progressive disclosure.** Read linked conventions and tool setup only when needed;
   do not preload architecture documents, all Skills or a Repomix dump.
10. **Graceful fallback.** If Serena or grepai is unavailable or its index is stale, use scoped `rg`, bounded reads
    and standard edits. Refresh grepai with `grepai index` when needed; keep working without optional tools.

