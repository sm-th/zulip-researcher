# Guest runs as root inside the microVM; Kubernetes must run non-root

The researcher guest image runs as uid 0 (root). This is acceptable today because
the isolation boundary is the Microsandbox microVM (ADR-0002), not the in-guest
uid: a compromised agent is confined by hardware virtualization, network-bound
secrets, and egress control, so dropping privileges *inside* the VM adds little to
the threat model (prompt-injection -> exfiltration, not container escape).
`dockerTools.fakeNss` only lets uid 0 resolve (`/etc/passwd`, `/etc/group`,
`nsswitch.conf`); it grants no privilege — without it `msb` exec fails with
"failed to resolve guest uid 0".

If/when the researcher is deployed as a Kubernetes pod (no microVM boundary),
root-in-container shares the host kernel and is unsafe. That path MUST run
non-root: `runAsNonRoot` with a dedicated uid, a writable `HOME` and clone dirs,
`drop: [ALL]` capabilities, a read-only root filesystem, a seccomp profile, and
Pod Security Standards "restricted". Until a k8s deployment actually exists we keep
root for simplicity rather than build non-root plumbing (writable HOME, XDG/omp
state, `/tmp` clone dirs) that nothing exercises yet.
