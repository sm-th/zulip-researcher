# Web reading runs in isolated, no-access sub-agents

The Research agent holds credentials and can write the repos, but it never browses the
open web itself. All fetching and reading of untrusted web pages is delegated to
sub-agents that have no secrets, no repo access, and no ability to act: they take a URL
or a query, return extracted text, and nothing else. The credential-holding agent only
ever sees already-extracted text, not live web content, so a prompt-injected page cannot
reach a secret or cause a write. This is the structural mitigation that makes the
single-VM model (ADR-0002) acceptable.
