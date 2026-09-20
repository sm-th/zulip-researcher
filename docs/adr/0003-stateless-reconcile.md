# Stateless: reconcile from Zulip and repo receipts, no local datastore

The listener keeps no local database. Idempotency is derived by reconciliation each
poll: Zulip reactions/markers say what has been answered, and receipts committed next
to the published artifacts (mirroring the telegram publisher's sibling state files)
say what has been published. We rejected a durable local journal because the external
systems already hold the ground truth durably, and a second store would only add a
sync problem — a lesson from the previous version (meno), whose in-memory state forced
fragile fresh-restart cycles.
