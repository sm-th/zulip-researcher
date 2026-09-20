# Everything runs in a microsandbox; the host only launches the VM

The entire system — the Zulip event loop, Recommend, Research, and every push/PR — runs
inside a Microsandbox VM, mirroring the zulip-publisher `sandbox` flake app. The host holds
nothing but the script that launches the VM and forwards secrets. Inside, the agent has a
full toolset (file edits, semantic search, web search, git) and does the work directly
rather than returning a payload for a host process to apply. For v1 the VM is launched by
hand; later it moves to Kubernetes.
