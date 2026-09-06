from __future__ import annotations

from sqlalchemy.orm import Session

from choice_agent.db_models import UserProfileRecord
from choice_agent.schemas import UserProfile


class ProfileRepository:
    def __init__(self, db: Session, *, commit: bool = True):
        self.db = db
        self.commit = commit

    def get(self, user_id: int) -> UserProfile:
        row = self.db.get(UserProfileRecord, user_id)
        if row is None:
            return UserProfile()
        return UserProfile.model_validate(row.profile_json)

    def save(self, user_id: int, profile: UserProfile) -> UserProfile:
        data = profile.model_dump(mode="json", by_alias=True)
        row = self.db.get(UserProfileRecord, user_id)
        if row is None:
            row = UserProfileRecord(user_id=user_id, profile_json=data)
            self.db.add(row)
        else:
            row.profile_json = data
        if self.commit:
            self.db.commit()
        else:
            self.db.flush()
        return profile
