from alembic import context
from hermeneut.research.config import ResearchSettings
from hermeneut.research.schema import engine_for, metadata

settings = ResearchSettings.from_env()
if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine_for(settings.database_url).connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
