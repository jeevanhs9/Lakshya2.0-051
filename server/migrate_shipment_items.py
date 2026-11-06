"""Add shipment manifests and backfill existing order-to-shipment links.

This migration is additive and idempotent. It never drops or reseeds data.
Run it once before starting the API after upgrading the backend.
"""

import os
import uuid
import json
import math

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, update
from sqlalchemy.orm import sessionmaker

from models import Order, ProduceListing, Shipment, ShipmentItem


SERVER_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(SERVER_DIR, '..', '.env'))
DB_PATH = os.path.join(SERVER_DIR, 'farmlink.db')
DATABASE_URL = os.environ.get('FARMLINK_DATABASE_URL') or f'sqlite:///{DB_PATH}'
engine_options = {'pool_pre_ping': True}
if DATABASE_URL.startswith('sqlite:'):
    engine_options['connect_args'] = {'check_same_thread': False, 'timeout': 30}
engine = create_engine(DATABASE_URL, **engine_options)
Session = sessionmaker(bind=engine)

SHIPMENT_ITEM_STATUS = {
    'Draft': 'reserved',
    'Confirmed': 'reserved',
    'Scheduled': 'scheduled',
    'In Transit': 'in_transit',
    'Disrupted': 'disrupted',
    'Delivered': 'delivered',
    'Cancelled': 'cancelled',
}


def migrate():
    required_tables = {'orders', 'shipments', 'shipment_stops', 'produce_listings'}
    existing_tables = set(inspect(engine).get_table_names())
    if not required_tables.issubset(existing_tables):
        raise RuntimeError('The existing FarmLink schema is incomplete; restore or initialize the database first.')
    ShipmentItem.__table__.create(engine, checkfirst=True)
    db = Session()
    created_order_items = 0
    created_listing_items = 0
    manual_review = set()
    try:
        shipments = {shipment.id: shipment for shipment in db.query(Shipment).all()}
        listings = {listing.id: listing for listing in db.query(ProduceListing).all()}
        known_order_ids = {order.id for order in db.query(Order).all()}
        linked_orders = db.query(Order).filter(Order.shipment_id.isnot(None)).all()
        for order in linked_orders:
            shipment = shipments.get(order.shipment_id)
            if not shipment or order.stage == 'Cancelled' or shipment.status == 'Cancelled':
                continue
            if db.query(ShipmentItem.id).filter(
                ShipmentItem.order_id == order.id,
                ShipmentItem.shipment_id == shipment.id,
            ).first():
                continue

            shipment_item_status = SHIPMENT_ITEM_STATUS.get(shipment.status, 'reserved')
            db.add(ShipmentItem(
                id=f'SI-{uuid.uuid4().hex[:16].upper()}',
                shipment_id=shipment.id,
                listing_id=order.listing_id,
                order_id=order.id,
                quantity=order.quantity,
                unit=order.unit,
                status=shipment_item_status,
            ))
            created_order_items += 1

            # A live shipment is the source of truth for delivery progress.
            if shipment.status == 'In Transit' and order.stage not in {'Delivered', 'Cancelled'}:
                order.stage = 'In Transit'
                order.is_disrupted = False
            elif shipment.status == 'Delivered' and order.stage != 'Cancelled':
                order.stage = 'Delivered'
                order.is_disrupted = False
            elif shipment.status == 'Disrupted' and order.stage not in {'Delivered', 'Cancelled'}:
                order.is_disrupted = True
                order.disruption_reason = f'Shipment {shipment.id} is disrupted.'

        db.flush()

        # The previous pooling endpoint put listing IDs in stop orderIds but did
        # not store a manifest or reserve the selected stock. Recover those
        # lines only when the remaining listing stock exactly accounts for the
        # shipment's otherwise-unexplained payload.
        active_item_statuses = {'cancelled', 'released', 'delivered'}
        for shipment in shipments.values():
            if shipment.status in {'Delivered', 'Cancelled'}:
                continue
            stop_references = set()
            for stop in shipment.stops:
                try:
                    references = json.loads(stop.order_ids_json or '[]')
                except (TypeError, ValueError):
                    references = []
                if isinstance(references, list):
                    stop_references.update(ref for ref in references if isinstance(ref, str))

            referenced_listings = {
                ref for ref in stop_references
                if ref in listings and ref not in known_order_ids
            }
            already_manifested = {
                item.listing_id for item in db.query(ShipmentItem).filter(
                    ShipmentItem.shipment_id == shipment.id,
                    ShipmentItem.listing_id.isnot(None),
                ).all()
            }
            candidate_ids = referenced_listings - already_manifested
            if candidate_ids:
                current_items = db.query(ShipmentItem).filter(
                    ShipmentItem.shipment_id == shipment.id,
                    ShipmentItem.status.notin_(active_item_statuses),
                ).all()
                known_payload = sum(item.quantity for item in current_items if item.unit == 'kg')
                candidate_listings = [listings[listing_id] for listing_id in sorted(candidate_ids)]
                candidate_payload = sum(listing.available_quantity for listing in candidate_listings)
                has_other_reservation = any(
                    db.query(ShipmentItem.id).filter(
                        ShipmentItem.listing_id == listing.id,
                        ShipmentItem.order_id.is_(None),
                        ShipmentItem.shipment_id != shipment.id,
                        ShipmentItem.status.notin_(active_item_statuses),
                    ).first()
                    for listing in candidate_listings
                )
                can_reconcile = (
                    not has_other_reservation
                    and all(listing.unit == 'kg' and listing.available_quantity > 0 for listing in candidate_listings)
                    and math.isclose(known_payload + candidate_payload, shipment.current_payload_kg or 0.0, abs_tol=0.01)
                )
                if can_reconcile:
                    for listing in candidate_listings:
                        reserved_quantity = listing.available_quantity
                        reserved = db.execute(
                            update(ProduceListing)
                            .where(
                                ProduceListing.id == listing.id,
                                ProduceListing.available_quantity == reserved_quantity,
                            )
                            .values(available_quantity=0.0)
                        )
                        if reserved.rowcount != 1:
                            raise RuntimeError(
                                f'Listing {listing.id} changed while migrating shipment {shipment.id}; retry the migration.'
                            )
                        db.add(ShipmentItem(
                            id=f'SI-{uuid.uuid4().hex[:16].upper()}',
                            shipment_id=shipment.id,
                            listing_id=listing.id,
                            quantity=reserved_quantity,
                            unit=listing.unit,
                            status=SHIPMENT_ITEM_STATUS.get(shipment.status, 'reserved'),
                        ))
                        created_listing_items += 1
                    db.flush()
                else:
                    manual_review.add(shipment.id)

            # Drop only dangling stop references that do not identify any
            # persisted order or listing. Keep valid but unmanifested records
            # untouched and report them for review.
            invalid_references = stop_references - known_order_ids - set(listings)
            if invalid_references:
                for stop in shipment.stops:
                    try:
                        references = json.loads(stop.order_ids_json or '[]')
                    except (TypeError, ValueError):
                        continue
                    if isinstance(references, list):
                        stop.order_ids_json = json.dumps([
                            ref for ref in references
                            if not isinstance(ref, str) or ref not in invalid_references
                        ])

            items = db.query(ShipmentItem).filter(
                ShipmentItem.shipment_id == shipment.id,
                ShipmentItem.status.notin_(active_item_statuses),
            ).all()
            manifested_refs = {
                item.order_id for item in items if item.order_id
            } | {
                item.listing_id for item in items if item.listing_id
            }
            unresolved_valid_refs = (
                stop_references & (known_order_ids | set(listings))
            ) - manifested_refs
            if unresolved_valid_refs:
                manual_review.add(shipment.id)
            elif items and all(item.unit == 'kg' for item in items):
                shipment.current_payload_kg = sum(item.quantity for item in items)

        db.commit()
        print(
            'Shipment manifest migration complete; '
            f'added {created_order_items} order line(s) and {created_listing_items} pooled listing line(s).'
        )
        if manual_review:
            print('Shipments requiring manual manifest review: ' + ', '.join(sorted(manual_review)))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        engine.dispose()


if __name__ == '__main__':
    migrate()
