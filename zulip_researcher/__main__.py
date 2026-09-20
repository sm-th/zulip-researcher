"""CLI.

  python -m zulip_researcher run     poll forever
  python -m zulip_researcher once    one reconcile pass, then exit
  python -m zulip_researcher show    read-only: list #research topics + reactions

Set RESEARCHER_DRY_RUN=1 to run without mutating Zulip, git, or Bluesky.
"""

from __future__ import annotations

import sys

from . import config


def _cmd_show(cfg: config.Config) -> int:
    from . import zulip
    zc = zulip.Zulip(cfg.zulip_url, cfg.zulip_api_key, cfg.zulip_api_username)
    stream_id = zc.get_stream_id(cfg.research_stream)
    for topic in zc.get_topics(stream_id):
        name = topic.get("name", "")
        msg = zc.first_message(stream_id, name)
        if not msg:
            continue
        reactions = [r.get("emoji_name") for r in msg.get("reactions", []) if r.get("emoji_name")]
        print(f"[{msg['id']}] {name}  reactions={reactions}")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    # Help must never touch configuration or secrets.
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    cmd = argv[0]
    if cmd not in ("run", "once", "show"):
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2

    try:
        cfg = config.load()
    except config.ConfigError as e:
        print(str(e), file=sys.stderr)
        return 2

    if cmd == "show":
        return _cmd_show(cfg)

    from . import loop, modes
    lp = loop.Loop(cfg, modes=modes.build(cfg))
    if cmd == "run":
        lp.run()
    else:
        lp.run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
