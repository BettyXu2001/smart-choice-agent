import pytest

from choice_agent.domains.registry import DomainRegistry


def test_registry_resolves_travel_from_message():
    plugin = DomainRegistry().resolve("周末从上海出发两天一夜，不想太累")
    assert plugin.key == "travel"


def test_registry_resolves_explicit_domain():
    plugin = DomainRegistry().resolve("今晚想吃清淡一点", explicit_domain="diet")
    assert plugin.key == "diet"
    assert plugin.metadata.complete is True


def test_registry_rejects_unknown_domain():
    with pytest.raises(ValueError, match="未知决策领域"):
        DomainRegistry().resolve("随便选点什么", explicit_domain="unknown")