from __future__ import annotations

from choice_agent.config import Settings
from choice_agent.domains.diet.profile import DietProfile
from choice_agent.domains.generic import GenericProfile
from choice_agent.domains.profile import DomainProfile
from choice_agent.domains.shopping import ShoppingProfile
from choice_agent.domains.travel import TravelProfile
from choice_agent.providers.model import DisabledProvider


class DomainRegistry:
    def __init__(self, profiles: list[DomainProfile] | None = None):
        resolved = profiles or default_profiles()
        self._profiles = {profile.key: profile for profile in resolved}

    def get(self, key: str) -> DomainProfile:
        normalized = (key or "").strip().lower()
        if normalized not in self._profiles:
            raise ValueError(f"未知决策领域：{key}")
        return self._profiles[normalized]

    def resolve(self, message: str, explicit_domain: str | None = None) -> DomainProfile:
        return self.get(self.identify(message, explicit_domain)["domain"])

    def identify(self, message: str, explicit_domain: str | None = None) -> dict:
        import re
        if explicit_domain:
            key = self.get(explicit_domain).key
            return {"domain": key, "candidateDomains": [key], "needsClarification": False, "question": None}
        text = message.lower()
        cues = {
            "diet": r"吃什么|想吃|早餐|午餐|晚餐|三餐|饮食|用餐|夜宵|吃点|餐食",
            "travel": r"去.{1,8}玩|旅行|旅游|目的地|两天一夜|\d+天.{0,5}游|从.{2,10}出发|travel|trip",
            "shopping": r"笔记本|电脑|手机|耳机|家电|冰箱|洗衣机|laptop|headphone|shopping",
        }
        candidates = [key for key, pattern in cues.items() if key in self._profiles and re.search(pattern,text)]
        key = candidates[0] if len(candidates) == 1 else "generic"
        return {"domain": key, "candidateDomains": candidates, "needsClarification": len(candidates) > 1,
                "question": "这次先聊饮食、旅行还是购物？也可以继续在通用决策里比较。" if len(candidates)>1 else None}

    def metadata(self):
        return [profile.metadata for profile in self._profiles.values()]


def default_profiles() -> list[DomainProfile]:
    return [
        DietProfile(None, Settings(), DisabledProvider()),
        TravelProfile(),
        ShoppingProfile(),
        GenericProfile(),
    ]