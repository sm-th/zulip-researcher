# Smith Wiki edits land via pull request, not direct to main

A Research pushes its wiki pages on a branch and opens a PR rather than committing to
`main`. This keeps each Research's edit reviewable as a unit in the history and revertible
in one go, at the cost of the page going live only on merge. The Zulip reply and the
Bluesky post use the deterministic final URL (`smith.wiki/<slug>/`); Bluesky publication is
gated until the page is live, reusing the publisher's link-blocks-until-target-published
mechanism.
