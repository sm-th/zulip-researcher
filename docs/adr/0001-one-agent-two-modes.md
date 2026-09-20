# One small agent, not two — and no module ceremony

Recommend and Research are two behaviours of one agent in one repo, sharing one codebase,
one Zulip seam and one wiki. They are not split into separate agents, services, or even
ceremoniously separate modules: the surface is small and will not proliferate (there will
not be two modes today and twenty tomorrow). This is a deliberate reaction to the previous
version (meno), which over-grew into a god-object; the fix is fewer moving parts, not a
formal internal split.
