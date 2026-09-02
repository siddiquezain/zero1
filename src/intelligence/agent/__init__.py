"""
Fire Intelligence Agent — a READ-ONLY natural-language layer over src/intelligence.

Guaranteed baseline: the deterministic keyword parser (works offline, no API key).
Optional enhancement: Claude, used only when ANTHROPIC_API_KEY is set and the
`anthropic` package imports. Both use the SAME read-only tool registry.

The agent can query / rank / filter / navigate / focus the map / open an
investigation / generate a read-only report. It CANNOT acknowledge, escalate,
resolve, delete, modify records, run SQL, run shell, or execute arbitrary code.
"""
from src.intelligence.agent.runtime import ask, AgentReply  # noqa: F401
