"""Copy the FarmLink SQLite database into an empty PostgreSQL database.

This one-time migration is intentionally conservative: it creates the current
schema, copies rows in foreign-key order, and exits before changing a target
that already contains FarmLink application records.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, inspect, select

from models import Base


SERVER_DIR = Path(__file__).resolve().parent
load_dotenv(SERVER_DIR.parent / '.env')
SOURCE_URL = os.environ.get('FARMLINK_SQLITE_SOURCE_URL') or (
    f"sqlite:///{(SERVER_DIR / 'farmlink.db').as_posix()}"
)
TARGET_URL = os.environ.get('FARMLINK_DATABASE_URL')


def create_engine_for(url):
    options = {'pool_pre_ping': True}
    if url.startswith('sqlite:'):
        options['connect_args'] = {'check_same_thread': False, 'timeout': 30}
    return create_engine(url, **options)


def migrate():
    if not TARGET_URL or not TARGET_URL.startswith('postgresql'):
        raise RuntimeError(
            'Set FARMLINK_DATABASE_URL to a PostgreSQL SQLAlchemy URL before running this migration.'
        )
    if TARGET_URL == SOURCE_URL:
        raise RuntimeError('Source and target databases must be different.')

    source_engine = create_engine_for(SOURCE_URL)
    target_engine = create_engine_for(TARGET_URL)
    try:
        source_tables = set(inspect(source_engine).get_table_names())
        required_tables = set(Base.metadata.tables)
        missing = required_tables - source_tables
        if missing:
            raise RuntimeError(
                'The SQLite source is missing required table(s): ' + ', '.join(sorted(missing)) + '.'
            )

        Base.metadata.create_all(target_engine)
        with target_engine.connect() as connection:
            populated_tables = [
                table.name for table in Base.metadata.sorted_tables
                if connection.execute(select(func.count()).select_from(table)).scalar_one() > 0
            ]
        if populated_tables:
            raise RuntimeError(
                'The PostgreSQL target already contains FarmLink data in: '
                + ', '.join(populated_tables)
                + '. Use an empty database to prevent overwriting data.'
            )

        copied_counts = []
        with source_engine.connect() as source, target_engine.begin() as target:
            for table in Base.metadata.sorted_tables:
                rows = [dict(row) for row in source.execute(select(table)).mappings()]
                if rows:
                    target.execute(table.insert(), rows)
                copied_counts.append((table.name, len(rows)))

            # Explicit primary-key values from SQLite do not advance PostgreSQL
            # sequences. Align each generated integer key so the next API write
            # receives an unused value.
            for table in Base.metadata.sorted_tables:
                for column in table.primary_key.columns:
                    if not isinstance(column.type.python_type(), int) or column.autoincrement is False:
                        continue
                    target.execute(
                        select(func.setval(
                            func.pg_get_serial_sequence(table.name, column.name),
                            func.coalesce(func.max(column), 1),
                            func.count(column) > 0,
                        )).select_from(table)
                    )

        print('PostgreSQL migration complete.')
        for table_name, row_count in copied_counts:
            print(f'  {table_name}: {row_count} row(s) copied')
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == '__main__':
    migrate()
