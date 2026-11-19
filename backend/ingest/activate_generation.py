from __future__ import annotations

import argparse
from uuid import UUID

from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import Session

from app.config import settings
from ingest.generations import activate_run


def _database_url() -> str:
    url = make_url(settings.database_url.get_secret_value())
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Activate a verified corpus generation")
    parser.add_argument("generation_id", type=UUID)
    args = parser.parse_args()
    engine = create_engine(_database_url(), pool_pre_ping=True)
    try:
        with Session(engine) as session:
            run = activate_run(session, args.generation_id)
            print(f"Activated corpus generation {run.id}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
