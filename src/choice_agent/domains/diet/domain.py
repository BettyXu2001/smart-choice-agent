from __future__ import annotations

from choice_agent.config import Settings
from choice_agent.domains.diet.profile import DietProfile
from choice_agent.providers.model import DisabledProvider


class DietDomain(DietProfile):
    """Compatibility name for callers that only need Diet metadata or matching."""

    def __init__(self):
        super().__init__(None, Settings(), DisabledProvider())