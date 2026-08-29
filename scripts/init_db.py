from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.domains.diet.seed import seed_legacy_data


def main() -> None:
    database = Database(Settings.from_env())
    database.create_all()
    with database.session_factory() as db:
        seed_legacy_data(db)
    print("Choice Agent V2 database initialized.")


if __name__ == "__main__":
    main()
