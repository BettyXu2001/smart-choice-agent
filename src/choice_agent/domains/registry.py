from __future__ import annotations

from choice_agent.domains.base import DomainMetadata, DomainPlugin
from choice_agent.domains.diet.domain import DietDomain
from choice_agent.domains.travel import TravelDomain


class DomainRegistry:
    def __init__(self, plugins: list[DomainPlugin] | None = None):
        self._plugins = {plugin.key: plugin for plugin in (plugins or default_plugins())}

    def get(self, key: str) -> DomainPlugin:
        normalized = (key or "").strip().lower()
        if normalized not in self._plugins:
            raise ValueError(f"未知决策领域：{key}")
        return self._plugins[normalized]

    def resolve(self, message: str, explicit_domain: str | None = None) -> DomainPlugin:
        if explicit_domain:
            return self.get(explicit_domain)
        for plugin in self._plugins.values():
            if plugin.matches(message):
                return plugin
        return self.get("travel")

    def metadata(self) -> list[DomainMetadata]:
        return [plugin.metadata for plugin in self._plugins.values()]


def default_plugins() -> list[DomainPlugin]:
    return [DietDomain(), TravelDomain()]