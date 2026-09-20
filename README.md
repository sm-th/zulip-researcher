# zulip-researcher

A Zulip bot that turns chat discussions into deep, sourced research.

Mention `@research` in any thread and it reads the discussion and suggests focused
research questions. Copy the ones worth pursuing into the `#research` channel; for each,
the bot runs deep, web-grounded research and publishes the result three ways — a short
answer back in the thread, a cited page on a wiki (via pull request), and a post on
Bluesky. It runs entirely inside a microsandbox.

- Vocabulary: [`CONTEXT.md`](CONTEXT.md)
- Decisions: [`docs/adr/`](docs/adr/)
- Agent notes & the privacy rule: [`AGENTS.md`](AGENTS.md)

## Run

    nix run .#debug   -- once   # SecretSpec + Python dev mode
    nix run .#sandbox -- run    # Microsandbox microVM

Non-secret structure lives in `zulip_researcher.toml` (git-ignored; copy from
`zulip_researcher.toml.example`); secrets are declared in `secretspec.toml`.
