# Everything runs in one microsandbox VM; the host only launches it

The whole system — the deterministic Zulip listener and every omp Recommend/Research
subprocess — runs inside a single Microsandbox VM, mirroring the zulip-publisher
`sandbox` app. The host holds nothing but the script that launches the VM and forwards
secrets. The image bundles omp plus git and the package.

The single-VM choice keeps secrets as plain env in the same VM the agent runs in. The
exfiltration risk that would create is contained structurally by ADR-0007: the
credential-holding agent never reads untrusted web content directly — that is delegated
to isolated, no-access sub-agents — so the process that can act on secrets never ingests
the prompt-injection surface. We rejected the previous system's per-task microVM with
network-bound secrets as more machinery than this model needs.
