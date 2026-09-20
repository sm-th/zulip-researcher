# Two single-identity Bluesky repos, not one dual-identity repo

Bluesky output is split across two publishing repos, one per account — the operator's
(`andysmith.ai`) and the agent's (`smith.wiki`) — each mirroring the telegram publisher
(flat `posts/` + CI + claim-first sibling state). This avoids juggling two identities and
two credentials inside one publisher. The `#research` exchange still mirrors to Bluesky as
a reply-thread across the two accounts; the cross-account parent reference (the parent
post's AT-URI, known only after its CI runs) is carried between repos via receipts.
