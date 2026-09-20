"""CLI.

  run                          poll forever
  once                         one reconcile pass, then exit
  show                         list #research topics + reactions
  doctor                       preflight: creds present + systems reachable (read-only)
  recommend <stream> <topic>   run Recommend once on a thread
  research <topic>             run Research once on a #research topic

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


def _trigger(stream: str, topic: str, *, is_mention: bool, is_topic_start: bool):
    from .loop import Trigger
    return Trigger(stream=stream, topic=topic, author_id=0, message_id=0,
                   is_mention=is_mention, is_topic_start=is_topic_start)


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    cmd = argv[0]
    if cmd not in ("run", "once", "show", "doctor", "recommend", "research"):
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2

    # doctor is read-only and loads config itself (it must report missing config too).
    if cmd == "doctor":
        from . import doctor
        return doctor.run()

    try:
        cfg = config.load()
        if cmd in ("run", "once", "recommend", "research"):
            cfg.validate_for_publish()
    except config.ConfigError as e:
        print(str(e), file=sys.stderr)
        return 2

    if cmd == "show":
        return _cmd_show(cfg)

    from . import modes
    m = modes.build(cfg)

    if cmd == "recommend":
        if len(argv) < 3:
            print("usage: recommend <stream> <topic>", file=sys.stderr)
            return 2
        m.recommend(_trigger(argv[1], argv[2], is_mention=True, is_topic_start=False))
        return 0

    if cmd == "research":
        if len(argv) < 2:
            print("usage: research <topic>", file=sys.stderr)
            return 2
        m.research(_trigger(cfg.research_stream, argv[1], is_mention=False, is_topic_start=True),
                   resume=False)
        return 0

    from . import loop
    lp = loop.Loop(cfg, modes=m)
    if cmd == "run":
        lp.run()
    else:
        lp.run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
