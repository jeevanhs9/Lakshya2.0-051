"""Add persistent GPS location history for shipment tracking.

This migration is additive and safe to run repeatedly.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

from models import ShipmentLocation


SERVER_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(SERVER_DIR, '..', '.env'))
DATABASE_URL = os.environ.get('FARMLINK_DATABASE_URL') or f"sqlite:///{os.path.join(SERVER_DIR, 'farmlink.db')}"
engine_options = {'pool_pre_ping': True}
if DATABASE_URL.startswith('sqlite:'):
    engine_options['connect_args'] = {'check_same_thread': False, 'timeout': 30}
engine = create_engine(DATABASE_URL, **engine_options)


def migrate():
    if 'shipments' not in inspect(engine).get_table_names():
        raise RuntimeError('The FarmLink shipments table is missing. Initialize or migrate the database first.')
    ShipmentLocation.__table__.create(engine, checkfirst=True)
    print('Shipment GPS location table is ready.')


if __name__ == '__main__':
    try:
        migrate()
    finally:
        engine.dispose()
