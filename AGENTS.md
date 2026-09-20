# zulip-researcher — agent notes

A Zulip bot that turns chat discussions into deep, sourced research: `@research` in a
thread suggests research questions; the operator copies chosen ones into `#research`,
where each auto-runs a deep, web-grounded Research published to the wiki (via pull
request) and mirrored to Bluesky. Everything runs inside a microsandbox; the host only
launches the VM. See `CONTEXT.md` for vocabulary and `docs/adr/` for decisions.

## Hard rule: nothing private in committed files or public output

This repo and everything it publishes (wiki pages, Bluesky posts) are treated as
public. Therefore:

- **No live links, real URLs, domains, handles, account names, or emails** in any
  committed file. Use generic placeholders (`example.com`, `you@example.com`,
  `https://github.com/you/your-repo.git`).
- **No machine/config details** of the operator's computer — absolute paths, host
  names, local layout. Real values live only in the operator's runtime config
  (`zulip_researcher.toml`, git-ignored) and in secrets (secretspec), never committed.
- Research output is **Clean**: it carries only what the result needs — no operator
  context, no Seed-thread detail, no back-link to where it came from.

Privacy is structural, not a prompt (see `docs/adr/0004-privacy-by-structure.md`).

## Module seams

- `config.py` — frozen `Config` dataclass; secrets from env, structure from TOML.
- `zulip.py` — the only Zulip seam (messages, topics, reactions, event queue).
- `prepare.py` — client for the preparation interface (normalizes operator input into clean, publishable markdown).

## Conventions

- Secrets come from `os.environ` only; declared (no values) in `secretspec.toml`.
- Non-secret structure in `zulip_researcher.toml`, every key overridable by a
  `RESEARCHER_*` env var.
- Run: `nix run .#debug -- once` (secretspec) or `nix run .#sandbox -- run` (microVM).
