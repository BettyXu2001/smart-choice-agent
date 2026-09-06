from __future__ import annotations

from choice_agent.repositories.profile_repository import ProfileRepository
from choice_agent.schemas import UserProfile


def test_profile_defaults_to_empty_values(database):
    with database.session_factory() as db:
        profile = ProfileRepository(db).get(7)

        assert profile.budget_habit is None
        assert profile.preferred_cities == []
        assert profile.diet_preferences == []
        assert profile.notes is None


def test_profile_save_and_user_isolation(database):
    with database.session_factory() as db:
        repository = ProfileRepository(db)
        repository.save(
            7,
            UserProfile(
                budget_habit="预算偏保守",
                preferred_cities=["上海", "杭州"],
                diet_preferences=["清淡"],
                notes="更看重稳定性",
            ),
        )

        own = repository.get(7)
        other = repository.get(8)

        assert own.budget_habit == "预算偏保守"
        assert own.preferred_cities == ["上海", "杭州"]
        assert own.diet_preferences == ["清淡"]
        assert own.notes == "更看重稳定性"
        assert other.budget_habit is None


def test_profile_api_functions_default_save_and_isolate_users(database):
    from choice_agent.api.routes import get_profile, save_profile

    with database.session_factory() as db:
        default = get_profile(uid=7, db=db)
        assert default.preferred_cities == []

        saved = save_profile(
            UserProfile(
                budget_habit="预算偏保守",
                preferred_cities=["上海"],
                diet_preferences=["清淡"],
                notes="更看重稳定性",
            ),
            uid=7,
            db=db,
        )
        assert saved.preferred_cities == ["上海"]
        assert get_profile(uid=8, db=db).preferred_cities == []
