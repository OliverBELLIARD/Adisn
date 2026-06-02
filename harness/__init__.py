"""Public package entry points for the Adisn harness."""

from harness.core.agent import HarnessAgent


def create_harness(
    safe_global: bool = False,
    compact_threshold_ratio: float = 0.85,
) -> HarnessAgent:
    """Build a harness instance rooted at the current workspace."""
    return HarnessAgent(
        safe_global=safe_global,
        compact_threshold_ratio=compact_threshold_ratio,
    )


def harness() -> HarnessAgent:
    """Alias used by the existing entry points."""
    return create_harness()
