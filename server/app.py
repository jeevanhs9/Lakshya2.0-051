"""
FarmLink AI — Flask REST API Service
Provides endpoints for authentication, produce listings, orders, intelligent load pooling,
offer comparison, disruption recovery, demand forecasting, live analytics, and SAP gateway.
"""

import os
import json
import uuid
import math
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from werkzeug.exceptions import HTTPException
from flask_cors import CORS
from sqlalchemy import create_engine, desc, text, update, case, or_
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from models import (
    Base, User, ProduceListing, Order, BuyerOffer, Shipment, ShipmentStop,
    ShipmentItem, ShipmentLocation, DisruptionEvent, AuditLog, Notification
)
from pooling_engine import (
    PoolingEngine, are_crops_compatible, select_best_vehicle,
    calculate_separate_cost, calculate_pooled_cost
)
from matching_engine import MatchingEngine
from pricing_engine import PricingEngine, compute_offer_financials
from forecasting_engine import ForecastingEngine
from sap_adapter import SAPEnterpriseAdapter
from routing_service import RoutingService, RoutingServiceError

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

DB_PATH = os.path.join(os.path.dirname(__file__), 'farmlink.db')
DATABASE_URL = os.environ.get('FARMLINK_DATABASE_URL') or f'sqlite:///{DB_PATH}'
engine_options = {'pool_pre_ping': True}
if DATABASE_URL.startswith('sqlite:'):
    engine_options['connect_args'] = {'check_same_thread': False, 'timeout': 30}
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine)

app = Flask(__name__)
allowed_origins = [
    origin.strip()
    for origin in (os.environ.get('FARMLINK_CORS_ORIGINS') or
                   'http://localhost:5173,http://127.0.0.1:5173').split(',')
    if origin.strip()
]
CORS(app, resources={r"/api/*": {"origins": allowed_origins}})


@app.errorhandler(HTTPException)
def handle_http_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': error.description}), error.code
    return error


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.exception('Unhandled request error')
    if request.path.startswith('/api/'):
        return jsonify({'error': 'An unexpected server error occurred.'}), 500
    return 'An unexpected server error occurred.', 500

VALID_PAYMENT_METHODS = {'UPI', 'Credit / Debit Card', 'Net Banking', 'Cash on Delivery'}
VALID_CORRIDORS = {'Bengaluru East', 'Bengaluru North', 'Bengaluru Central', 'Mysuru Hub'}
LOCATION_COORDINATES = {
    'kolar': (13.1358, 78.1326),
    'chikkaballapur': (13.4350, 77.7315),
    'tumakuru': (13.3409, 77.1010),
    'tumkur': (13.3409, 77.1010),
    'mandya': (12.5218, 76.8951),
    'bengaluru east': (12.9784, 77.6408),
    'indiranagar': (12.9784, 77.6408),
    'bengaluru north': (13.0358, 77.5970),
    'hebbal': (13.0358, 77.5970),
    'yelahanka': (13.1007, 77.5963),
    'bengaluru central': (12.9860, 77.5940),
    'vasanth nagar': (12.9860, 77.5940),
    'bengaluru': (12.9716, 77.5946),
    'mysuru': (12.2958, 76.6394),
    'mysore': (12.2958, 76.6394),
}

pooling_engine = PoolingEngine()
matching_engine = MatchingEngine()
pricing_engine = PricingEngine()
forecasting_engine = ForecastingEngine()
sap_adapter = SAPEnterpriseAdapter()
routing_service = RoutingService(
    api_key=os.environ.get('GEOAPIFY_API_KEY') or os.environ.get('GOOGLE_MAPS_SERVER_API_KEY'),
    provider='geoapify' if os.environ.get('GEOAPIFY_API_KEY') else 'google',
    region=os.environ.get('FARMLINK_GEOCODE_REGION', 'in'),
)


def coordinates_for_location(location):
    normalized = (location or '').strip().lower()
    for place, coordinates in LOCATION_COORDINATES.items():
        if place in normalized:
            return coordinates
    try:
        resolved = routing_service.geocode(location)
        if resolved:
            return resolved
    except RoutingServiceError:
        app.logger.warning('Could not geocode location through the configured routing provider.')
    return None


def calculate_driving_route(coordinates):
    try:
        return routing_service.route(coordinates)
    except RoutingServiceError:
        app.logger.warning('Could not calculate a driving route through the configured routing provider.')
        return None


def shipment_item_status(shipment_status):
    return {
        'Draft': 'reserved',
        'Confirmed': 'reserved',
        'Scheduled': 'scheduled',
        'In Transit': 'in_transit',
        'Disrupted': 'disrupted',
        'Delivered': 'delivered',
        'Cancelled': 'cancelled',
    }.get(shipment_status, 'reserved')


def remove_order_from_stops(shipment, order_id):
    for stop in shipment.stops:
        try:
            order_ids = json.loads(stop.order_ids_json or '[]')
        except (TypeError, ValueError):
            order_ids = []
        if order_id in order_ids:
            remaining_ids = [item for item in order_ids if item != order_id]
            stop.order_ids_json = json.dumps(remaining_ids)
            if not remaining_ids and stop.stop_type == 'delivery':
                stop.status = 'Cancelled'


def release_listing_inventory(db, listing_id, quantity):
    return db.execute(
        update(ProduceListing)
        .where(ProduceListing.id == listing_id)
        .values(available_quantity=case(
            (ProduceListing.available_quantity + quantity <= ProduceListing.quantity,
             ProduceListing.available_quantity + quantity),
            else_=ProduceListing.quantity,
        ))
    ).rowcount == 1


def corridor_for_location(location):
    normalized = (location or '').lower()
    if 'mysuru' in normalized or 'mysore' in normalized:
        return 'Mysuru Hub'
    if any(place in normalized for place in ('east', 'indiranagar', 'mahadevapura')):
        return 'Bengaluru East'
    if any(place in normalized for place in ('north', 'hebbal', 'yelahanka', 'yeshwanthpur')):
        return 'Bengaluru North'
    return 'Bengaluru Central'

def get_db():
    return SessionLocal()


def parse_number(value, field_name, allow_zero=False):
    if isinstance(value, bool):
        raise ValueError(f'{field_name} must be a number.')
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field_name} must be a number.')
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        qualifier = 'zero or greater' if allow_zero else 'greater than zero'
        raise ValueError(f'{field_name} must be {qualifier}.')
    return number


def require_text(value, field_name, max_length, min_length=1):
    if not isinstance(value, str):
        raise ValueError(f'{field_name} is required.')
    value = value.strip()
    if len(value) < min_length:
        raise ValueError(f'{field_name} is required.')
    if len(value) > max_length:
        raise ValueError(f'{field_name} must be {max_length} characters or fewer.')
    return value


def new_record_id(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:12].upper()}'


def parse_coordinate(value, field_name, minimum, maximum):
    coordinate = parse_number(value, field_name, allow_zero=True)
    if coordinate < minimum or coordinate > maximum:
        raise ValueError(f'{field_name} must be between {minimum} and {maximum}.')
    return coordinate

def log_audit(session, action, entity_type, entity_id, actor_id='system', actor_role='system', details=None):
    entry = AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=json.dumps(details or {}),
        created_at=datetime.now(timezone.utc)
    )
    session.add(entry)

# ----------------- HEALTH & CONFIG -----------------
@app.route('/api/health', methods=['GET'])
def health():
    db = get_db()
    try:
        db.execute(text('SELECT 1'))
        db.execute(text('SELECT 1 FROM shipment_items LIMIT 1'))
        return jsonify({
            'status': 'healthy',
            'service': 'FarmLink AI Engine API',
            'version': '2.0.0',
            'database': 'reachable',
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    except Exception:
        app.logger.exception('Database health check failed')
        return jsonify({'status': 'unhealthy', 'error': 'Database unavailable or migration required'}), 503
    finally:
        db.close()

# ----------------- AUTHENTICATION -----------------
@app.route('/api/auth/demo-login', methods=['POST'])
def demo_login():
    data = request.get_json(silent=True)
    if data is None and request.get_data(cache=True).strip():
        return jsonify({'error': 'Request body must be valid JSON.'}), 400
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    try:
        role = require_text(data.get('role'), 'Role', 30).lower()
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    if role not in {'farmer', 'buyer', 'fpo', 'logistics', 'admin'}:
        return jsonify({'error': 'Unsupported demo role.'}), 400
    db = get_db()
    try:
        user = db.query(User).filter(User.role == role, User.is_active.is_(True)).first()
        if not user:
            return jsonify({'error': 'No active demo user is configured for this role.'}), 404

        log_audit(db, 'USER_LOGIN', 'USER', user.id, actor_id=user.id, actor_role=user.role, details={'role': role})
        db.commit()
        return jsonify({
            'success': True,
            'mode': 'demo',
            'user': user.to_dict(),
        })
    finally:
        db.close()

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    user_id = request.args.get('userId', 'f1')
    db = get_db()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify({'user': user.to_dict()})
    finally:
        db.close()

# ----------------- PRODUCE LISTINGS -----------------
@app.route('/api/products', methods=['GET'])
def list_products():
    db = get_db()
    try:
        category = request.args.get('category')
        farmer_id = request.args.get('farmerId')
        query_text = request.args.get('q', '').lower()

        q = db.query(ProduceListing).filter(ProduceListing.is_active == True)
        if category and category != 'All':
            q = q.filter(ProduceListing.category == category)
        if farmer_id:
            q = q.filter(ProduceListing.farmer_id == farmer_id)

        all_listings = q.order_by(desc(ProduceListing.created_at)).all()
        results = [l.to_dict() for l in all_listings]

        if query_text:
            results = [
                r for r in results
                if query_text in r['name'].lower()
                or query_text in r['location'].lower()
                or query_text in r['farmer'].lower()
            ]

        return jsonify({'products': results, 'count': len(results)})
    finally:
        db.close()

@app.route('/api/products/<product_id>', methods=['GET'])
def get_product(product_id):
    db = get_db()
    try:
        item = db.query(ProduceListing).filter(ProduceListing.id == product_id).first()
        if not item:
            return jsonify({'error': 'Product not found'}), 404
        return jsonify({'product': item.to_dict()})
    finally:
        db.close()

@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400

    try:
        farmer_id = require_text(data.get('farmerId'), 'farmerId', 50)
        name = require_text(data.get('name'), 'Produce name', 100)
        category = require_text(data.get('category', 'Vegetables'), 'Category', 50)
        quantity = parse_number(data.get('quantity'), 'Quantity')
        price = parse_number(data.get('price'), 'Price')
        unit = require_text(data.get('unit', 'kg'), 'Unit', 20)
        location = require_text(data.get('location'), 'Location', 150)
        quality = require_text(data.get('quality', 'Grade A'), 'Quality', 50)
        harvest_date = data.get('harvestDate') or datetime.now().strftime('%Y-%m-%d')
        if not isinstance(harvest_date, str) or len(harvest_date) > 30:
            raise ValueError('Harvest date must be a valid date string of 30 characters or fewer.')
        description = data.get('description', '')
        if not isinstance(description, str) or len(description) > 5000:
            raise ValueError('Description must be 5000 characters or fewer.')
        image = data.get('image')
        if image is not None and (not isinstance(image, str) or len(image) > 500):
            raise ValueError('Image URL must be 500 characters or fewer.')
    except ValueError as error:
        return jsonify({'error': str(error)}), 400

    db = get_db()
    try:
        farmer = db.query(User).filter(
            User.id == farmer_id,
            User.is_active.is_(True),
            User.role.in_(['farmer', 'fpo'])
        ).first()
        if not farmer:
            return jsonify({'error': 'An active farmer or FPO user is required.'}), 400

        new_id = new_record_id('p')

        listing = ProduceListing(
            id=new_id,
            farmer_id=farmer_id,
            name=name,
            category=category,
            quantity=quantity,
            available_quantity=quantity,
            unit=unit,
            price=price,
            quality=quality,
            harvest_date=harvest_date,
            location=location,
            demand='Medium',
            image=image or 'https://images.unsplash.com/photo-1546094096-0df4bcaaa337?q=80&w=800&auto=format&fit=crop',
            description=description,
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        db.add(listing)
        log_audit(db, 'LISTING_CREATED', 'PRODUCE_LISTING', new_id, actor_id=farmer_id, actor_role=farmer.role,
                  details={'name': name, 'quantity': quantity, 'price': price})
        db.commit()
        return jsonify({'success': True, 'product': listing.to_dict()}), 201
    except Exception:
        db.rollback()
        app.logger.exception('Unable to create produce listing')
        return jsonify({'error': 'Unable to create listing.'}), 500
    finally:
        db.close()

@app.route('/api/products/<product_id>', methods=['PUT'])
def update_product(product_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400

    try:
        if 'name' in data:
            data['name'] = require_text(data['name'], 'Produce name', 100)
        if 'price' in data:
            data['price'] = parse_number(data['price'], 'Price')
        if 'quantity' in data:
            data['quantity'] = parse_number(data['quantity'], 'Quantity', allow_zero=True)
        if 'quality' in data:
            data['quality'] = require_text(data['quality'], 'Quality', 50)
        if 'location' in data:
            data['location'] = require_text(data['location'], 'Location', 150)
        if 'description' in data and (not isinstance(data['description'], str) or len(data['description']) > 5000):
            raise ValueError('Description must be 5000 characters or fewer.')
    except ValueError as error:
        return jsonify({'error': str(error)}), 400

    db = get_db()
    try:
        listing = db.query(ProduceListing).filter(ProduceListing.id == product_id).first()
        if not listing:
            return jsonify({'error': 'Listing not found'}), 404

        if 'name' in data:
            listing.name = data['name']
        if 'price' in data:
            listing.price = data['price']
        if 'quantity' in data:
            diff = data['quantity'] - listing.available_quantity
            listing.available_quantity = data['quantity']
            listing.quantity += diff
        if 'quality' in data:
            listing.quality = data['quality']
        if 'location' in data:
            listing.location = data['location']
        if 'description' in data:
            listing.description = data['description']

        log_audit(db, 'LISTING_UPDATED', 'PRODUCE_LISTING', product_id, details=data)
        db.commit()
        return jsonify({'success': True, 'product': listing.to_dict()})
    except Exception:
        db.rollback()
        app.logger.exception('Unable to update produce listing %s', product_id)
        return jsonify({'error': 'Unable to update listing.'}), 500
    finally:
        db.close()

@app.route('/api/products/<product_id>', methods=['DELETE'])
def delete_product(product_id):
    db = get_db()
    try:
        listing = db.query(ProduceListing).filter(ProduceListing.id == product_id).first()
        if not listing:
            return jsonify({'error': 'Listing not found'}), 404

        # Soft delete / deactivate
        listing.is_active = False
        log_audit(db, 'LISTING_DEACTIVATED', 'PRODUCE_LISTING', product_id)
        db.commit()
        return jsonify({'success': True, 'message': f'Listing {product_id} deactivated'})
    finally:
        db.close()

# ----------------- ORDERS -----------------
@app.route('/api/orders', methods=['GET'])
def list_orders():
    db = get_db()
    try:
        buyer_id = request.args.get('buyerId')
        farmer_id = request.args.get('farmerId')
        stage = request.args.get('stage')

        q = db.query(Order)
        if buyer_id:
            q = q.filter(Order.buyer_id == buyer_id)
        if farmer_id:
            q = q.filter(Order.farmer_id == farmer_id)
        if stage:
            q = q.filter(Order.stage == stage)

        all_orders = q.order_by(desc(Order.created_at)).all()
        return jsonify({'orders': [o.to_dict() for o in all_orders]})
    finally:
        db.close()

@app.route('/api/orders', methods=['POST'])
def place_order():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400

    items = data.get('items')
    if not isinstance(items, list) or not items:
        return jsonify({'error': 'Cart is empty. Select produce to order.'}), 400
    if len(items) > 50:
        return jsonify({'error': 'An order can contain at most 50 produce lots.'}), 400

    try:
        buyer_id = require_text(data.get('buyerId'), 'buyerId', 50)
        delivery_location = require_text(data.get('deliveryLocation'), 'Delivery location', 255, min_length=5)
        payment_method = require_text(data.get('paymentMethod', 'UPI'), 'Payment method', 50)
        if payment_method not in VALID_PAYMENT_METHODS:
            raise ValueError('Choose a supported payment method.')
        validated_items = []
        product_ids = set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Each cart item must be a JSON object.')
            product_id = require_text(item.get('productId'), 'Product ID', 50)
            if product_id in product_ids:
                raise ValueError('Each produce lot can appear only once in a cart.')
            product_ids.add(product_id)
            quantity = parse_number(item.get('quantity'), 'Quantity')
            validated_items.append((product_id, quantity))
    except ValueError as error:
        return jsonify({'error': str(error)}), 400

    db = get_db()
    created_orders = []
    try:
        buyer = db.query(User).filter(
            User.id == buyer_id,
            User.is_active.is_(True),
            User.role == 'buyer'
        ).first()
        if not buyer:
            return jsonify({'error': 'An active buyer account is required.'}), 400
        buyer_name = buyer.org_name or buyer.name

        # Validate the entire cart before touching inventory so a bad line cannot
        # leave a partially-created order behind.
        products = []
        for product_id, quantity in validated_items:
            product = db.query(ProduceListing).filter(
                ProduceListing.id == product_id,
                ProduceListing.is_active.is_(True)
            ).first()
            if not product:
                return jsonify({'error': f'Product {product_id} not found'}), 404
            if product.available_quantity < quantity:
                return jsonify({
                    'error': f'Insufficient stock for {product.name}. Only {product.available_quantity} {product.unit} available.'
                }), 400
            products.append((product, quantity))

        for product, quantity in products:
            # Conditional SQL update prevents concurrent checkouts from selling
            # more stock than the listing has available.
            stock_update = db.execute(
                update(ProduceListing)
                .where(
                    ProduceListing.id == product.id,
                    ProduceListing.is_active.is_(True),
                    ProduceListing.available_quantity >= quantity
                )
                .values(available_quantity=ProduceListing.available_quantity - quantity)
            )
            if stock_update.rowcount != 1:
                db.rollback()
                return jsonify({'error': f'Availability changed for {product.name}. Refresh the cart and try again.'}), 409
            db.refresh(product)

            subtotal = round(product.price * quantity, 2)
            logistics_fee = round(subtotal * 0.08, 2)
            platform_fee = round(subtotal * 0.02, 2)
            total = round(subtotal + logistics_fee + platform_fee, 2)

            new_order_id = new_record_id('ORD')
            now = datetime.now(timezone.utc)

            new_order = Order(
                id=new_order_id,
                buyer_id=buyer_id,
                buyer_name=buyer_name,
                farmer_id=product.farmer_id,
                farmer_name=product.farmer.org_name if product.farmer else "Farmer Collective",
                listing_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit=product.unit,
                subtotal=subtotal,
                logistics_fee=logistics_fee,
                platform_fee=platform_fee,
                total=total,
                payment_method=payment_method,
                stage='Order Placed',
                placed_on=now.date().isoformat(),
                eta=(now + timedelta(days=3)).date().isoformat(),
                delivery_location=delivery_location,
                created_at=now
            )
            db.add(new_order)
            created_orders.append(new_order)

            log_audit(db, 'ORDER_PLACED', 'ORDER', new_order_id, actor_id=buyer_id, actor_role='buyer',
                      details={'product': product.name, 'quantity': quantity, 'total': total})

        for farmer_id in {order.farmer_id for order in created_orders}:
            farmer_orders = [order for order in created_orders if order.farmer_id == farmer_id]
            first_order = farmer_orders[0]
            db.add(Notification(
                id=new_record_id('notif'),
                user_id=farmer_id,
                role='farmer',
                title=f"New Order Placed: {len(farmer_orders)} lot(s)",
                message=f"{buyer_name} placed an order for {first_order.product_name} ({first_order.quantity} {first_order.unit}).",
                tone='info',
                link='/farmer/orders',
                created_at=datetime.now(timezone.utc)
            ))

        db.commit()
        return jsonify({'success': True, 'orders': [o.to_dict() for o in created_orders]}), 201
    except Exception:
        db.rollback()
        app.logger.exception('Unable to place order')
        return jsonify({'error': 'Unable to place order.'}), 500
    finally:
        db.close()

ORDER_STAGES = ['Order Placed', 'Confirmed', 'Packed', 'Picked Up', 'In Transit', 'Delivered']

@app.route('/api/orders/<order_id>/stage', methods=['PATCH'])
def advance_order_stage(order_id):
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404

        data = request.get_json(silent=True)
        if data is None and request.get_data(cache=True).strip():
            return jsonify({'error': 'Request body must be valid JSON.'}), 400
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return jsonify({'error': 'A JSON object is required.'}), 400
        target_stage = data.get('stage')

        current_stage = order.stage
        if target_stage:
            if target_stage not in ORDER_STAGES:
                return jsonify({'error': f'Invalid stage: {target_stage}'}), 400
            current_idx = ORDER_STAGES.index(current_stage) if current_stage in ORDER_STAGES else -1
            if current_idx < 0 or current_idx >= len(ORDER_STAGES) - 1:
                return jsonify({'error': f'Order cannot move from {order.stage}.'}), 409
            expected_stage = ORDER_STAGES[current_idx + 1]
            if target_stage != expected_stage:
                return jsonify({'error': f'Order can move only to {expected_stage} next.'}), 409
            next_stage = expected_stage
        else:
            current_idx = ORDER_STAGES.index(current_stage) if current_stage in ORDER_STAGES else -1
            if current_idx < 0:
                return jsonify({'error': f'Order cannot move from {order.stage}.'}), 409
            if current_idx >= len(ORDER_STAGES) - 1:
                return jsonify({'error': f'Order cannot move from {order.stage}.'}), 409
            next_stage = ORDER_STAGES[current_idx + 1]

        if next_stage in {'Picked Up', 'In Transit', 'Delivered'}:
            if not order.shipment_id:
                return jsonify({'error': 'Assign this packed order to a shipment before pickup.'}), 409
            return jsonify({'error': 'Shipment progress controls pickup and delivery status for this order.'}), 409

        transition = db.execute(
            update(Order)
            .where(Order.id == order_id, Order.stage == current_stage)
            .values(stage=next_stage)
        )
        if transition.rowcount != 1:
            db.rollback()
            return jsonify({'error': 'Order status changed. Refresh and try again.'}), 409
        db.refresh(order)

        log_audit(db, 'ORDER_STAGE_UPDATED', 'ORDER', order_id, details={'new_stage': order.stage})
        db.commit()
        return jsonify({'success': True, 'order': order.to_dict()})
    finally:
        db.close()

@app.route('/api/orders/<order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    data = request.get_json(silent=True)
    if data is None and request.get_data(cache=True).strip():
        return jsonify({'error': 'Request body must be valid JSON.'}), 400
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    try:
        reason = require_text(data.get('reason', 'Buyer cancellation request'), 'Cancellation reason', 255)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400

    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404

        current_stage = order.stage
        if current_stage == 'Cancelled':
            return jsonify({'error': 'Order is already cancelled.'}), 409
        if current_stage == 'Delivered':
            return jsonify({'error': 'A delivered order cannot be cancelled.'}), 409
        if current_stage not in {'Order Placed', 'Confirmed', 'Packed'}:
            return jsonify({'error': 'An order cannot be cancelled after pickup. Report a shipment disruption instead.'}), 409

        prior_shipment_id = order.shipment_id
        shipment = None
        shipment_item = None
        if prior_shipment_id:
            shipment = db.query(Shipment).filter(Shipment.id == prior_shipment_id).with_for_update().first()
            if not shipment or shipment.status not in {'Confirmed', 'Scheduled'}:
                return jsonify({'error': 'The assigned shipment has already departed; cancel it through shipment recovery.'}), 409
            shipment_item = db.query(ShipmentItem).filter(
                ShipmentItem.order_id == order.id,
                ShipmentItem.shipment_id == shipment.id,
            ).with_for_update().first()
            if not shipment_item or shipment_item.shipment_id != shipment.id:
                return jsonify({'error': 'The order shipment manifest is inconsistent. Refresh or contact logistics.'}), 409

        expected_shipment = Order.shipment_id.is_(None) if prior_shipment_id is None else Order.shipment_id == prior_shipment_id
        cancellation = db.execute(
            update(Order)
            .where(Order.id == order_id, Order.stage == current_stage, expected_shipment)
            .values(stage='Cancelled', is_disrupted=True, disruption_reason=reason, shipment_id=None)
        )
        if cancellation.rowcount != 1:
            db.rollback()
            return jsonify({'error': 'Order status changed. Refresh and try again.'}), 409
        db.refresh(order)

        # The order reservation was deducted at checkout. Restore it once, and
        # remove its manifest line if the truck has not left the depot.
        if order.listing_id and not release_listing_inventory(db, order.listing_id, order.quantity):
            db.rollback()
            return jsonify({'error': 'Could not restore inventory. No cancellation was saved.'}), 409

        if shipment and shipment_item:
            shipment_item.status = 'cancelled'
            remove_order_from_stops(shipment, order.id)
            active_items = db.query(ShipmentItem).filter(
                ShipmentItem.shipment_id == shipment.id,
                ShipmentItem.status.notin_(['cancelled', 'released', 'delivered'])
            ).all()
            shipment.current_payload_kg = sum(item.quantity for item in active_items)
            if not active_items:
                shipment.status = 'Cancelled'
                shipment.current_payload_kg = 0.0
                for stop in shipment.stops:
                    stop.status = 'Cancelled'

        # Create Disruption Event record for recovery workflow
        disruption_id = f"DISR-{uuid.uuid4().hex[:8].upper()}"
        disruption = DisruptionEvent(
            id=disruption_id,
            order_id=order.id,
            shipment_id=prior_shipment_id,
            event_type='cancellation',
            severity='high',
            description=f"Cancellation on {order.id}: {reason}. Harvested batch of {order.quantity} {order.unit} {order.product_name} needs re-matching.",
            affected_crop=order.product_name,
            affected_quantity=order.quantity,
            original_buyer_id=order.buyer_id,
            status='open',
            created_at=datetime.now(timezone.utc)
        )
        db.add(disruption)

        # Notify Farmer of disruption
        db.add(Notification(
            id=f"notif-{uuid.uuid4().hex[:10]}",
            user_id=order.farmer_id,
            role='farmer',
            title=f"Order Cancelled: {order.id}",
            message=f"{order.buyer_name} cancelled {order.quantity} {order.unit} {order.product_name}. Open Disruption Recovery to match alternative buyers.",
            tone='error',
            link='/disruptions',
            created_at=datetime.now(timezone.utc)
        ))

        log_audit(db, 'ORDER_CANCELLED', 'ORDER', order_id, details={'reason': reason, 'disruption_id': disruption_id})
        db.commit()
        return jsonify({'success': True, 'order': order.to_dict(), 'disruption': disruption.to_dict()})
    finally:
        db.close()

# ----------------- LOAD POOLING -----------------
@app.route('/api/pooling/opportunities', methods=['GET'])
def get_pooling_opportunities():
    db = get_db()
    try:
        corridor = request.args.get('corridor', 'Bengaluru East')
        try:
            corridor = require_text(corridor, 'Destination corridor', 80)
        except ValueError as error:
            return jsonify({'error': str(error)}), 400
        if corridor not in VALID_CORRIDORS:
            return jsonify({'error': 'Unsupported destination corridor.'}), 400

        listings = db.query(ProduceListing).filter(
            ProduceListing.is_active.is_(True),
            ProduceListing.available_quantity > 0,
            ProduceListing.unit == 'kg'
        ).all()
        candidate_items = [l.to_dict() for l in listings]

        opportunities = pooling_engine.find_pooling_opportunities(candidate_items, destination_corridor=corridor)
        return jsonify({
            'opportunities': opportunities,
            'count': len(opportunities),
            'destinationCorridor': corridor
        })
    finally:
        db.close()

@app.route('/api/pooling/confirm', methods=['POST'])
def confirm_pool():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    item_ids = data.get('itemIds')
    if not isinstance(item_ids, list) or len(item_ids) < 2 or len(item_ids) > 50:
        return jsonify({'error': 'A pooled shipment requires 2 to 50 produce lots.'}), 400
    if not all(isinstance(item_id, str) for item_id in item_ids):
        return jsonify({'error': 'Produce lot IDs must be strings.'}), 400
    if len(set(item_ids)) != len(item_ids):
        return jsonify({'error': 'A produce lot can appear only once in a shipment.'}), 400
    try:
        item_ids = [require_text(item_id, 'Produce lot ID', 50) for item_id in item_ids]
        destination = require_text(data.get('destination'), 'Destination corridor', 80)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    if destination not in VALID_CORRIDORS:
        return jsonify({'error': 'Unsupported destination corridor.'}), 400

    db = get_db()
    try:
        listings = db.query(ProduceListing).filter(
            ProduceListing.id.in_(item_ids),
            ProduceListing.is_active.is_(True)
        ).all()
        if len(listings) != len(item_ids):
            return jsonify({'error': 'One or more selected lots are missing or inactive.'}), 404
        if any(listing.unit != 'kg' for listing in listings):
            return jsonify({'error': 'Load pooling currently accepts produce quantities measured in kilograms.'}), 400
        if any(listing.available_quantity <= 0 for listing in listings):
            return jsonify({'error': 'All selected lots must have available stock.'}), 409

        crops = [listing.name for listing in listings]
        if any(
            not are_crops_compatible(crops[index], crops[other_index])
            for index in range(len(crops))
            for other_index in range(index + 1, len(crops))
        ):
            return jsonify({'error': 'Selected crops have incompatible handling requirements.'}), 400

        total_quantity = sum(l.available_quantity for l in listings)
        vehicle = select_best_vehicle(total_quantity)
        if total_quantity > vehicle['capacity_kg']:
            return jsonify({'error': 'Selected lots exceed the largest supported vehicle capacity.'}), 409

        items_for_costing = [
            {'id': listing.id, 'product': listing.name, 'quantity': listing.available_quantity, 'location': listing.location}
            for listing in listings
        ]
        separate_cost = calculate_separate_cost(items_for_costing, destination)
        pooled_route = calculate_pooled_cost(items_for_costing, destination, vehicle)
        pooled_cost = pooled_route['pooled_cost_inr']
        savings = max(0.0, round(separate_cost - pooled_cost, 2))
        savings_pct = round(savings / separate_cost * 100, 1) if separate_cost > 0 else 0.0
        origin_locations = {
            listing.location.split(',')[0].strip(): listing.location
            for listing in listings
        }
        origins = sorted(origin_locations)
        origin_coordinates = {
            origin: coordinates_for_location(location)
            for origin, location in origin_locations.items()
        }
        if any(coordinates is None for coordinates in origin_coordinates.values()):
            return jsonify({'error': 'A pickup location has no configured route coordinates.'}), 400
        destination_coordinates = coordinates_for_location(destination)
        if destination_coordinates is None:
            return jsonify({'error': 'The destination has no configured route coordinates.'}), 400
        driving_route = calculate_driving_route(
            [origin_coordinates[origin] for origin in origins] + [destination_coordinates]
        )

        # Reserve the stock in the same transaction as shipment creation. This
        # prevents the same lot from being pooled twice or sold from the marketplace.
        reserved_quantities = {}
        for listing in listings:
            reserved_quantity = listing.available_quantity
            reserved_quantities[listing.id] = reserved_quantity
            reservation = db.execute(
                update(ProduceListing)
                .where(
                    ProduceListing.id == listing.id,
                    ProduceListing.is_active.is_(True),
                    ProduceListing.available_quantity >= reserved_quantity
                )
                .values(available_quantity=ProduceListing.available_quantity - reserved_quantity)
            )
            if reservation.rowcount != 1:
                db.rollback()
                return jsonify({'error': 'Produce availability changed. Refresh pooling opportunities and try again.'}), 409

        shipment_id = new_record_id('SHP')

        new_shipment = Shipment(
            id=shipment_id,
            vehicle_id='KA-04-TR-8821',
            vehicle_name=vehicle['name'],
            vehicle_capacity_kg=vehicle['capacity_kg'],
            current_payload_kg=total_quantity,
            status='Confirmed',
            origin=f"{', '.join(origins)} FPO Hubs",
            destination=destination,
            planned_distance_km=driving_route['distanceKm'] if driving_route else pooled_route['route_distance_km'],
            planned_duration_hours=driving_route['durationHours'] if driving_route else pooled_route['travel_time_hours'],
            baseline_cost=separate_cost,
            optimized_cost=pooled_cost,
            estimated_savings=savings,
            savings_pct=savings_pct,
            pooled_orders_count=len(listings),
            explanation=f"Confirmed consolidated run pooling {len(listings)} lots ({total_quantity} kg) from {', '.join(origins)} to {destination}.",
            created_at=datetime.now(timezone.utc)
        )
        db.add(new_shipment)
        db.flush()

        db.add_all([
            ShipmentItem(
                id=new_record_id('SI'),
                shipment_id=shipment_id,
                listing_id=listing.id,
                quantity=reserved_quantities[listing.id],
                unit=listing.unit,
                status='reserved',
            )
            for listing in listings
        ])

        # Add sequence of stops
        seq = 1
        for orig in origins:
            latitude, longitude = origin_coordinates[orig]
            stop = ShipmentStop(
                id=f"stop-{shipment_id}-{seq}",
                shipment_id=new_shipment.id,
                sequence=seq,
                stop_type='pickup',
                name=f"{orig} FPO Hub",
                location=f"{orig}, Karnataka",
                lat=latitude,
                lng=longitude,
                order_ids_json='[]',
                eta=(datetime(2000, 1, 1, 7, 30) + timedelta(hours=seq)).strftime('%I:%M %p'),
                status='Scheduled'
            )
            db.add(stop)
            seq += 1

        delivery_stop = ShipmentStop(
            id=f"stop-{shipment_id}-{seq}",
            shipment_id=new_shipment.id,
            sequence=seq,
            stop_type='delivery',
            name=f"{destination} Consolidation Depot",
            location=f"{destination}, Karnataka",
            lat=destination_coordinates[0],
            lng=destination_coordinates[1],
            order_ids_json='[]',
            eta='04:30 PM',
            status='Upcoming'
        )
        db.add(delivery_stop)

        for farmer_id in {listing.farmer_id for listing in listings}:
            farmer_lots = [listing for listing in listings if listing.farmer_id == farmer_id]
            db.add(Notification(
                id=new_record_id('notif'),
                user_id=farmer_id,
                role='farmer',
                title='Produce reserved for pooled shipment',
                message=f"{sum(reserved_quantities[listing.id] for listing in farmer_lots):g} kg of produce has been reserved for shipment {shipment_id}.",
                tone='info',
                link='/logistics',
                created_at=datetime.now(timezone.utc)
            ))

        log_audit(db, 'POOL_CONFIRMED', 'SHIPMENT', shipment_id,
                  details={'itemIds': item_ids, 'total_kg': total_quantity, 'savings_inr': savings})
        db.commit()

        return jsonify({'success': True, 'shipment': new_shipment.to_dict()}), 201
    except Exception:
        db.rollback()
        app.logger.exception('Unable to confirm pooled shipment')
        return jsonify({'error': 'Unable to confirm pooled shipment.'}), 500
    finally:
        db.close()

# ----------------- PRICE & BUYER OFFER COMPARISON -----------------
@app.route('/api/offers', methods=['GET'])
def list_offers():
    db = get_db()
    try:
        listing_id = request.args.get('listingId')
        q = db.query(BuyerOffer)
        if listing_id:
            q = q.filter(BuyerOffer.listing_id == listing_id)
        offers = q.order_by(desc(BuyerOffer.created_at)).all()
        return jsonify({'offers': [o.to_dict() for o in offers]})
    finally:
        db.close()

@app.route('/api/offers/compare', methods=['POST'])
def compare_offers():
    data = request.get_json(silent=True)
    if data is None and request.get_data(cache=True).strip():
        return jsonify({'error': 'Request body must be valid JSON.'}), 400
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    listing_id = data.get('listingId')
    priority = data.get('priority', 'max_net_proceeds')
    valid_priorities = {'max_net_proceeds', 'min_distance', 'fast_delivery'}
    if not isinstance(priority, str) or priority not in valid_priorities:
        return jsonify({'error': 'Unsupported offer comparison priority.'}), 400

    db = get_db()
    try:
        q = db.query(BuyerOffer).filter(BuyerOffer.status == 'pending')
        if listing_id is not None:
            if not isinstance(listing_id, str) or not listing_id.strip():
                return jsonify({'error': 'listingId must be a non-empty string.'}), 400
            q = q.filter(BuyerOffer.listing_id == listing_id)
        offers = q.all()

        offers_data = [o.to_dict() for o in offers]
        result = pricing_engine.compare_offers(offers_data, priority=priority)
        return jsonify(result)
    finally:
        db.close()

@app.route('/api/offers/<offer_id>/accept', methods=['POST'])
def accept_offer(offer_id):
    db = get_db()
    try:
        offer = db.query(BuyerOffer).filter(BuyerOffer.id == offer_id).first()
        if not offer:
            return jsonify({'error': 'Offer not found'}), 404
        if offer.status != 'pending':
            return jsonify({'error': 'Only pending offers can be accepted.'}), 409

        buyer = db.query(User).filter(
            User.id == offer.buyer_id,
            User.is_active.is_(True),
            User.role == 'buyer'
        ).first()
        listing = db.query(ProduceListing).filter(
            ProduceListing.id == offer.listing_id,
            ProduceListing.is_active.is_(True)
        ).first()
        if not buyer or not listing:
            return jsonify({'error': 'The buyer or active listing for this offer no longer exists.'}), 409

        offer_claim = db.execute(
            update(BuyerOffer)
            .where(BuyerOffer.id == offer_id, BuyerOffer.status == 'pending')
            .values(status='accepted')
        )
        if offer_claim.rowcount != 1:
            db.rollback()
            return jsonify({'error': 'This offer has already been accepted or is no longer pending.'}), 409
        db.refresh(offer)

        try:
            quantity = parse_number(offer.requested_quantity, 'Requested quantity')
            offered_price = parse_number(offer.offered_price, 'Offer price')
        except ValueError as error:
            return jsonify({'error': str(error)}), 409
        if listing.unit != offer.unit or listing.available_quantity < quantity:
            return jsonify({'error': 'The listing no longer has the requested quantity and unit.'}), 409

        stock_update = db.execute(
            update(ProduceListing)
            .where(
                ProduceListing.id == listing.id,
                ProduceListing.is_active.is_(True),
                ProduceListing.available_quantity >= quantity
            )
            .values(available_quantity=ProduceListing.available_quantity - quantity)
        )
        if stock_update.rowcount != 1:
            db.rollback()
            return jsonify({'error': 'Listing availability changed. Refresh offers before accepting.'}), 409
        db.refresh(listing)

        offer.buyer_name = buyer.org_name or buyer.name
        offer.crop_name = listing.name
        offer.offered_price = offered_price
        fin = compute_offer_financials(offer.to_dict())

        order_id = new_record_id('ORD')
        now = datetime.now(timezone.utc)
        new_order = Order(
            id=order_id,
            buyer_id=offer.buyer_id,
            buyer_name=offer.buyer_name,
            farmer_id=listing.farmer_id,
            farmer_name=listing.farmer.org_name or listing.farmer.name,
            listing_id=listing.id,
            product_name=listing.name,
            quantity=quantity,
            unit=listing.unit,
            subtotal=fin['grossRevenue'],
            logistics_fee=fin['estimatedFreight'],
            platform_fee=fin['platformFee'],
            total=round(fin['grossRevenue'] + fin['estimatedFreight'] + fin['platformFee'], 2),
            payment_method='Accepted Buyer Offer',
            stage='Confirmed',
            placed_on=now.date().isoformat(),
            eta=(now + timedelta(days=2)).date().isoformat(),
            delivery_location=offer.delivery_destination,
            created_at=now
        )
        db.add(new_order)
        db.add(Notification(
            id=new_record_id('notif'),
            user_id=listing.farmer_id,
            role='farmer',
            title=f"Offer accepted: {offer.crop_name}",
            message=f"{offer.buyer_name} accepted the offer for {quantity:g} {listing.unit} at ₹{offered_price:.2f} per {listing.unit}.",
            tone='success',
            link='/farmer/orders',
            created_at=now
        ))
        log_audit(db, 'OFFER_ACCEPTED', 'BUYER_OFFER', offer_id, details={'order_id': order_id, 'net_proceeds': fin['netProceeds']})
        db.commit()

        return jsonify({'success': True, 'order': new_order.to_dict(), 'offer': offer.to_dict()})
    except Exception:
        db.rollback()
        app.logger.exception('Unable to accept offer %s', offer_id)
        return jsonify({'error': 'Unable to accept offer.'}), 500
    finally:
        db.close()

# ----------------- DISRUPTION RECOVERY -----------------
@app.route('/api/disruptions', methods=['GET'])
def list_disruptions():
    db = get_db()
    try:
        status = request.args.get('status')
        q = db.query(DisruptionEvent)
        if status:
            q = q.filter(DisruptionEvent.status == status)
        events = q.order_by(desc(DisruptionEvent.created_at)).all()
        return jsonify({'disruptions': [e.to_dict() for e in events]})
    finally:
        db.close()

@app.route('/api/disruptions/<disruption_id>/matches', methods=['GET'])
def get_disruption_matches(disruption_id):
    db = get_db()
    try:
        disr = db.query(DisruptionEvent).filter(DisruptionEvent.id == disruption_id).first()
        if not disr:
            return jsonify({'error': 'Disruption event not found'}), 404
        if disr.status != 'open':
            return jsonify({'disruption': disr.to_dict(), 'alternativeBuyers': []})

        order = db.query(Order).filter(Order.id == disr.order_id).first() if disr.order_id else None
        if not order:
            return jsonify({
                'disruption': disr.to_dict(),
                'alternativeBuyers': [],
                'recoverable': False,
                'message': 'This disruption affects pooled shipment cargo and is resolved by resuming the shipment.',
            })
        listing = db.query(ProduceListing).filter(ProduceListing.id == order.listing_id).first() if order and order.listing_id else None
        crop = listing.name if listing else (disr.affected_crop or 'Tomato')
        quantity = order.quantity if order else (disr.affected_quantity or 180.0)
        asking_price = listing.price if listing else 30.0
        quality = listing.quality if listing else 'Grade A'
        origin = listing.location if listing else 'Kolar'

        registered_buyer_ids = {
            user.id for user in db.query(User).filter(
                User.role == 'buyer', User.is_active.is_(True)
            ).all()
        }
        matches = matching_engine.match_alternative_buyers(
            crop=crop,
            quantity_kg=quantity,
            asking_price_per_kg=asking_price,
            quality=quality,
            origin_location=origin,
            excluded_buyer_id=disr.original_buyer_id
        )
        matches = [candidate for candidate in matches if candidate['buyer_id'] in registered_buyer_ids]
        return jsonify({'disruption': disr.to_dict(), 'alternativeBuyers': matches})
    finally:
        db.close()

@app.route('/api/disruptions/<disruption_id>/recover', methods=['POST'])
def recover_disruption(disruption_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    try:
        chosen_buyer_id = require_text(data.get('buyerId'), 'Alternative buyer ID', 50)
        offered_price = parse_number(data.get('agreedPrice'), 'Agreed price')
    except ValueError as error:
        return jsonify({'error': str(error)}), 400

    db = get_db()
    try:
        disr = db.query(DisruptionEvent).filter(DisruptionEvent.id == disruption_id).with_for_update().first()
        if not disr:
            return jsonify({'error': 'Disruption event not found'}), 404
        if disr.status != 'open':
            return jsonify({'error': 'Only open disruption events can be recovered.'}), 409

        order = db.query(Order).filter(Order.id == disr.order_id).with_for_update().first() if disr.order_id else None
        if not order:
            return jsonify({'error': 'Disruption is not linked to an order that can be reassigned.'}), 409

        shipment = None
        shipment_item = None
        if order.shipment_id:
            shipment = db.query(Shipment).filter(Shipment.id == order.shipment_id).with_for_update().first()
            if not shipment or shipment.status != 'Disrupted' or disr.shipment_id != shipment.id:
                return jsonify({'error': 'An in-transit order can only be recovered through its disrupted shipment.'}), 409
            shipment_item = db.query(ShipmentItem).filter(
                ShipmentItem.shipment_id == shipment.id,
                ShipmentItem.order_id == order.id,
            ).with_for_update().first()
            if not shipment_item:
                return jsonify({'error': 'The disrupted order is missing from its shipment manifest.'}), 409
        elif order.stage != 'Cancelled':
            return jsonify({'error': 'Only a cancelled order or an order in a disrupted shipment can be reassigned.'}), 409

        buyer = db.query(User).filter(
            User.id == chosen_buyer_id,
            User.role == 'buyer',
            User.is_active.is_(True)
        ).first()
        if not buyer or chosen_buyer_id == disr.original_buyer_id:
            return jsonify({'error': 'Select an active alternative buyer.'}), 400
        buyer_coordinates = coordinates_for_location(buyer.location)
        if shipment and buyer_coordinates is None:
            return jsonify({'error': 'The alternative buyer has no configured route coordinates.'}), 409

        listing = db.query(ProduceListing).filter(ProduceListing.id == order.listing_id).first() if order.listing_id else None
        asking_price = listing.price if listing else 30.0
        crop = listing.name if listing else order.product_name
        quality = listing.quality if listing else 'Grade A'
        origin = listing.location if listing else 'Kolar'
        candidates = matching_engine.match_alternative_buyers(
            crop=crop,
            quantity_kg=order.quantity,
            asking_price_per_kg=asking_price,
            quality=quality,
            origin_location=origin,
            excluded_buyer_id=disr.original_buyer_id
        )
        candidate = next((item for item in candidates if item['buyer_id'] == chosen_buyer_id), None)
        if not candidate:
            return jsonify({'error': 'The selected buyer is not a valid recovery match.'}), 400
        if round(offered_price, 2) != round(candidate['estimated_offer_price'], 2):
            return jsonify({'error': 'Agreed price does not match the current buyer recommendation.'}), 400

        # A pre-dispatch cancellation released stock. Reserve it again for the
        # replacement buyer; shipments already in transit retain their payload.
        if order.shipment_id is None:
            if not listing or not listing.is_active:
                return jsonify({'error': 'The produce listing is no longer active.'}), 409
            stock_update = db.execute(
                update(ProduceListing)
                .where(
                    ProduceListing.id == listing.id,
                    ProduceListing.is_active.is_(True),
                    ProduceListing.available_quantity >= order.quantity
                )
                .values(available_quantity=ProduceListing.available_quantity - order.quantity)
            )
            if stock_update.rowcount != 1:
                db.rollback()
                return jsonify({'error': 'There is not enough available produce to reassign this order.'}), 409

        resolved = db.execute(
            update(DisruptionEvent)
            .where(DisruptionEvent.id == disruption_id, DisruptionEvent.status == 'open')
            .values(
                status='resolved',
                resolved_alternative_buyer_id=chosen_buyer_id,
                resolved_at=datetime.now(timezone.utc),
            )
        )
        if resolved.rowcount != 1:
            db.rollback()
            return jsonify({'error': 'This disruption was already resolved. Refresh and try again.'}), 409
        db.refresh(disr)

        now = datetime.now(timezone.utc)
        chosen_buyer_name = buyer.org_name or buyer.name
        subtotal = round(offered_price * order.quantity, 2)
        logistics_fee = round(subtotal * 0.08, 2)
        platform_fee = round(subtotal * 0.02, 2)

        disr.recovery_notes = (
            f"Successfully reallocated {order.quantity} {order.unit} of {order.product_name} "
            f"to {chosen_buyer_name} at ₹{offered_price:.2f}/{order.unit}, preventing harvest spoilage."
        )

        order.stage = 'In Transit' if shipment else 'Confirmed'
        order.buyer_id = chosen_buyer_id
        order.buyer_name = chosen_buyer_name
        order.subtotal = subtotal
        order.logistics_fee = logistics_fee
        order.platform_fee = platform_fee
        order.total = subtotal + logistics_fee + platform_fee
        order.is_disrupted = bool(shipment)
        order.disruption_reason = (
            f"Reassigned to {chosen_buyer_name}; shipment is awaiting resume."
            if shipment else f"Reassigned to {chosen_buyer_name} via Disruption Recovery"
        )
        order.delivery_location = buyer.location

        if shipment and shipment_item:
            remove_order_from_stops(shipment, order.id)
            next_sequence = max((stop.sequence for stop in shipment.stops), default=0) + 1
            db.add(ShipmentStop(
                id=f"stop-{shipment.id}-recovery-{uuid.uuid4().hex[:8]}",
                shipment_id=shipment.id,
                sequence=next_sequence,
                stop_type='delivery',
                name=f'Delivery to {chosen_buyer_name}',
                location=buyer.location,
                lat=buyer_coordinates[0],
                lng=buyer_coordinates[1],
                order_ids_json=json.dumps([order.id]),
                eta='ETA pending route update',
                status='Upcoming',
            ))
            shipment_item.status = 'disrupted'
            other_active_items = db.query(ShipmentItem.id).filter(
                ShipmentItem.shipment_id == shipment.id,
                ShipmentItem.id != shipment_item.id,
                ShipmentItem.status.notin_(['cancelled', 'released', 'delivered']),
            ).first()
            shipment.destination = (
                'Multi-stop route update required' if other_active_items else buyer.location[:150]
            )
            shipment.explanation = f"{shipment.explanation or ''} Route recalculation is required after the buyer reassignment.".strip()

        db.add(Notification(
            id=new_record_id('notif'),
            user_id=order.farmer_id,
            role='farmer',
            title=f"Order reassigned: {order.id}",
            message=f"{order.product_name} was reassigned to {chosen_buyer_name} at ₹{offered_price:.2f} per {order.unit}.",
            tone='success',
            link='/farmer/orders',
            created_at=now
        ))
        db.add(Notification(
            id=new_record_id('notif'),
            user_id=chosen_buyer_id,
            role='buyer',
            title=f'Order reassigned to you: {order.id}',
            message=f'{order.quantity:g} {order.unit} of {order.product_name} is assigned at ₹{offered_price:.2f} per {order.unit}.',
            tone='info',
            link='/buyer/orders',
            created_at=now,
        ))

        log_audit(db, 'DISRUPTION_RESOLVED', 'DISRUPTION_EVENT', disruption_id,
                  details={'new_buyer_id': chosen_buyer_id, 'agreed_price': offered_price})
        db.commit()

        return jsonify({'success': True, 'disruption': disr.to_dict(), 'order': order.to_dict()})
    except Exception:
        db.rollback()
        app.logger.exception('Unable to recover disruption %s', disruption_id)
        return jsonify({'error': 'Unable to recover disruption.'}), 500
    finally:
        db.close()

# ----------------- FORECASTING & SUPPLY GAPS -----------------
@app.route('/api/forecasting', methods=['GET'])
def get_forecasting():
    crop = request.args.get('crop', 'Tomato')
    location = request.args.get('location', 'Kolar')
    eval_result = forecasting_engine.evaluate_models(crop=crop, location=location)
    return jsonify(eval_result)

@app.route('/api/forecasting/gaps', methods=['GET'])
def get_supply_demand_gaps():
    db = get_db()
    try:
        listings = db.query(ProduceListing).filter(ProduceListing.is_active == True).all()
        listings_data = [l.to_dict() for l in listings]
        gaps = forecasting_engine.detect_supply_demand_gaps(listings_data)
        return jsonify({'gaps': gaps, 'evaluatedListings': len(listings_data)})
    finally:
        db.close()

# ----------------- SHIPMENTS & LOGISTICS -----------------
@app.route('/api/routing/geocode', methods=['GET'])
def geocode_address():
    try:
        address = require_text(request.args.get('address'), 'Address', 255)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    if not routing_service.configured:
        return jsonify({'error': 'Server geocoding is not configured.'}), 503
    try:
        coordinates = routing_service.geocode(address)
    except RoutingServiceError as error:
        return jsonify({'error': str(error)}), 502
    if not coordinates:
        return jsonify({'error': 'Address could not be geocoded.'}), 404
    return jsonify({
        'address': address,
        'position': {'lat': coordinates[0], 'lng': coordinates[1]},
        'provider': f'{routing_service.provider}_geocoding',
    })


@app.route('/api/routing/route', methods=['POST'])
def calculate_route():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('stops'), list):
        return jsonify({'error': 'A JSON object with a stops array is required.'}), 400
    stops = data['stops']
    if len(stops) < 2 or len(stops) > 25:
        return jsonify({'error': 'Provide between 2 and 25 route stops.'}), 400
    try:
        coordinates = [
            (
                parse_coordinate(stop.get('lat'), 'Latitude', -90, 90),
                parse_coordinate(stop.get('lng'), 'Longitude', -180, 180),
            )
            for stop in stops
            if isinstance(stop, dict)
        ]
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    if len(coordinates) != len(stops):
        return jsonify({'error': 'Each route stop must include latitude and longitude.'}), 400
    if not routing_service.configured:
        return jsonify({'error': 'Server routing is not configured.'}), 503
    try:
        route = routing_service.route(coordinates)
    except RoutingServiceError as error:
        return jsonify({'error': str(error)}), 502
    if not route:
        return jsonify({'error': 'No driving route was found for these stops.'}), 404
    return jsonify({'route': route})


@app.route('/api/shipments', methods=['GET'])
def list_shipments():
    db = get_db()
    try:
        shipments = db.query(Shipment).order_by(desc(Shipment.created_at)).all()
        return jsonify({'shipments': [s.to_dict() for s in shipments]})
    finally:
        db.close()


@app.route('/api/shipments/<shipment_id>/location', methods=['GET'])
def get_shipment_location(shipment_id):
    db = get_db()
    try:
        shipment = db.query(Shipment.id).filter(Shipment.id == shipment_id).first()
        if not shipment:
            return jsonify({'error': 'Shipment not found'}), 404
        location = db.query(ShipmentLocation).filter(
            ShipmentLocation.shipment_id == shipment_id
        ).order_by(desc(ShipmentLocation.recorded_at), desc(ShipmentLocation.id)).first()
        return jsonify({'location': location.to_dict() if location else None})
    finally:
        db.close()


@app.route('/api/shipments/<shipment_id>/location', methods=['POST'])
def record_shipment_location(shipment_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    try:
        latitude = parse_coordinate(data.get('latitude'), 'Latitude', -90, 90)
        longitude = parse_coordinate(data.get('longitude'), 'Longitude', -180, 180)
        accuracy = data.get('accuracyMeters')
        accuracy = parse_number(accuracy, 'Accuracy', allow_zero=True) if accuracy is not None else None
        if accuracy is not None and accuracy > 10000:
            raise ValueError('Accuracy must be 10,000 meters or lower.')
    except ValueError as error:
        return jsonify({'error': str(error)}), 400

    db = get_db()
    try:
        shipment = db.query(Shipment).filter(Shipment.id == shipment_id).with_for_update().first()
        if not shipment:
            return jsonify({'error': 'Shipment not found'}), 404
        if shipment.status not in {'In Transit', 'Disrupted'}:
            return jsonify({'error': 'GPS positions can only be reported for an in-transit or disrupted shipment.'}), 409

        location = ShipmentLocation(
            shipment_id=shipment_id,
            latitude=latitude,
            longitude=longitude,
            accuracy_meters=accuracy,
            source='browser_gps',
            recorded_at=datetime.now(timezone.utc),
            received_at=datetime.now(timezone.utc),
        )
        db.add(location)
        log_audit(db, 'SHIPMENT_LOCATION_REPORTED', 'SHIPMENT', shipment_id,
                  details={'latitude': latitude, 'longitude': longitude, 'accuracyMeters': accuracy})
        db.commit()
        return jsonify({'success': True, 'location': location.to_dict()}), 201
    except Exception:
        db.rollback()
        app.logger.exception('Unable to record shipment location for %s', shipment_id)
        return jsonify({'error': 'Unable to record shipment location.'}), 500
    finally:
        db.close()

@app.route('/api/shipments', methods=['POST'])
def create_shipment_from_orders():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    order_ids = data.get('orderIds')
    if not isinstance(order_ids, list) or not order_ids or len(order_ids) > 50:
        return jsonify({'error': 'Select between 1 and 50 packed orders for a shipment.'}), 400
    if not all(isinstance(order_id, str) for order_id in order_ids):
        return jsonify({'error': 'Order IDs must be strings.'}), 400
    if len(set(order_ids)) != len(order_ids):
        return jsonify({'error': 'An order can appear only once in a shipment.'}), 400

    db = get_db()
    try:
        orders = db.query(Order).filter(Order.id.in_(order_ids)).all()
        if len(orders) != len(order_ids):
            return jsonify({'error': 'One or more selected orders were not found.'}), 404
        if any(order.stage != 'Packed' or order.shipment_id or order.is_disrupted for order in orders):
            return jsonify({'error': 'Only packed, undisrupted orders without a shipment can be assigned.'}), 409
        if any(order.unit != 'kg' for order in orders):
            return jsonify({'error': 'Shipment assignment currently requires order quantities in kilograms.'}), 400

        listing_ids = {order.listing_id for order in orders if order.listing_id}
        listings = {
            listing.id: listing
            for listing in db.query(ProduceListing).filter(ProduceListing.id.in_(listing_ids)).all()
        }
        if any(not order.listing_id or order.listing_id not in listings for order in orders):
            return jsonify({'error': 'Every order must reference an existing produce listing.'}), 409

        buyers = {
            user.id: user
            for user in db.query(User).filter(User.id.in_({order.buyer_id for order in orders})).all()
        }
        if any(order.buyer_id not in buyers for order in orders):
            return jsonify({'error': 'Every order must reference an existing buyer.'}), 409

        pickup_locations = {listings[order.listing_id].location for order in orders}
        pickup_coordinates = {location: coordinates_for_location(location) for location in pickup_locations}
        for location, coordinates in pickup_coordinates.items():
            if coordinates is None:
                return jsonify({'error': f'No route coordinates are configured for pickup location: {location}.'}), 400
        buyer_coordinates = {
            buyer_id: coordinates_for_location(buyer.location)
            for buyer_id, buyer in buyers.items()
        }
        for order in orders:
            if buyer_coordinates[order.buyer_id] is None:
                return jsonify({'error': f'No route coordinates are configured for buyer {order.buyer_id}.'}), 400

        total_payload = sum(order.quantity for order in orders)
        vehicle = select_best_vehicle(total_payload)
        if total_payload > vehicle['capacity_kg']:
            return jsonify({'error': 'Selected orders exceed the largest supported vehicle capacity.'}), 409

        order_corridors = {corridor_for_location(buyers[order.buyer_id].location) for order in orders}
        if len(order_corridors) != 1:
            return jsonify({'error': 'Create separate shipments for orders in different destination corridors.'}), 400
        corridor = next(iter(order_corridors))
        route_items = [
            {
                'id': order.id,
                'product': order.product_name,
                'quantity': order.quantity,
                'location': listings[order.listing_id].location,
            }
            for order in orders
        ]
        separate_cost = calculate_separate_cost(route_items, corridor)
        pooled_route = calculate_pooled_cost(route_items, corridor, vehicle)
        shipment_id = new_record_id('SHP')
        now = datetime.now(timezone.utc)
        destinations = sorted({order.delivery_location for order in orders})
        origin_locations = {
            listings[order.listing_id].location.split(',')[0].strip(): listings[order.listing_id].location
            for order in orders
        }
        origins = sorted(origin_locations)
        origin_coordinates = {
            origin: pickup_coordinates[location]
            for origin, location in origin_locations.items()
        }
        delivery_coordinates = []
        seen_buyer_ids = set()
        for order in orders:
            if order.buyer_id not in seen_buyer_ids:
                delivery_coordinates.append(buyer_coordinates[order.buyer_id])
                seen_buyer_ids.add(order.buyer_id)
        driving_route = calculate_driving_route(
            [origin_coordinates[origin] for origin in origins] + delivery_coordinates
        )
        shipment = Shipment(
            id=shipment_id,
            vehicle_id=new_record_id('VEH'),
            vehicle_name=vehicle['name'],
            vehicle_capacity_kg=vehicle['capacity_kg'],
            current_payload_kg=total_payload,
            status='Confirmed',
            origin=f"{', '.join(origins)} FPO Hubs",
            destination='; '.join(destinations)[:150],
            planned_distance_km=driving_route['distanceKm'] if driving_route else pooled_route['route_distance_km'],
            planned_duration_hours=driving_route['durationHours'] if driving_route else pooled_route['travel_time_hours'],
            baseline_cost=separate_cost,
            optimized_cost=pooled_route['pooled_cost_inr'],
            estimated_savings=max(0.0, round(separate_cost - pooled_route['pooled_cost_inr'], 2)),
            savings_pct=round(max(0.0, separate_cost - pooled_route['pooled_cost_inr']) / separate_cost * 100, 1) if separate_cost else 0.0,
            pooled_orders_count=len(orders),
            explanation=f"Order shipment for {len(orders)} packed orders across {len(origins)} pickup hub(s). Route costs are estimates to the {corridor} corridor.",
            created_at=now,
        )
        db.add(shipment)
        db.flush()

        for order in orders:
            assignment = db.execute(
                update(Order)
                .where(
                    Order.id == order.id,
                    Order.stage == 'Packed',
                    Order.shipment_id.is_(None),
                    or_(Order.is_disrupted.is_(False), Order.is_disrupted.is_(None)),
                )
                .values(shipment_id=shipment_id)
            )
            if assignment.rowcount != 1:
                db.rollback()
                return jsonify({'error': 'An order changed while the shipment was being created. Refresh and try again.'}), 409
            db.refresh(order)
            db.add(ShipmentItem(
                id=new_record_id('SI'),
                shipment_id=shipment_id,
                listing_id=order.listing_id,
                order_id=order.id,
                quantity=order.quantity,
                unit=order.unit,
                status='reserved',
            ))

        sequence = 1
        for origin in origins:
            origin_orders = [order for order in orders if listings[order.listing_id].location.split(',')[0].strip() == origin]
            latitude, longitude = origin_coordinates[origin]
            db.add(ShipmentStop(
                id=f"stop-{shipment_id}-{sequence}",
                shipment_id=shipment_id,
                sequence=sequence,
                stop_type='pickup',
                name=f'{origin} FPO Hub',
                location=f'{origin}, Karnataka',
                lat=latitude,
                lng=longitude,
                order_ids_json=json.dumps([order.id for order in origin_orders]),
                eta=(datetime(2000, 1, 1, 7, 30) + timedelta(hours=sequence)).strftime('%I:%M %p'),
                status='Scheduled',
            ))
            sequence += 1

        delivery_groups = {}
        for order in orders:
            key = (order.delivery_location, order.buyer_id)
            delivery_groups.setdefault(key, []).append(order)
        for (delivery_location, buyer_id), destination_orders in delivery_groups.items():
            latitude, longitude = buyer_coordinates[buyer_id]
            db.add(ShipmentStop(
                id=f"stop-{shipment_id}-{sequence}",
                shipment_id=shipment_id,
                sequence=sequence,
                stop_type='delivery',
                name=f"Delivery to {buyers[buyer_id].org_name or buyers[buyer_id].name}",
                location=delivery_location[:200],
                lat=latitude,
                lng=longitude,
                order_ids_json=json.dumps([order.id for order in destination_orders]),
                eta=(datetime(2000, 1, 1, 7, 30) + timedelta(hours=sequence)).strftime('%I:%M %p'),
                status='Upcoming',
            ))
            sequence += 1

        for farmer_id in {order.farmer_id for order in orders}:
            db.add(Notification(
                id=new_record_id('notif'),
                user_id=farmer_id,
                role='farmer',
                title=f'Orders assigned to shipment {shipment_id}',
                message=f'{sum(order.quantity for order in orders if order.farmer_id == farmer_id):g} kg of packed produce is assigned to a confirmed shipment.',
                tone='info',
                link='/farmer/orders',
                created_at=now,
            ))

        log_audit(db, 'ORDERS_ASSIGNED_TO_SHIPMENT', 'SHIPMENT', shipment_id,
                  details={'orderIds': order_ids, 'payloadKg': total_payload})
        db.commit()
        return jsonify({'success': True, 'shipment': shipment.to_dict()}), 201
    except Exception:
        db.rollback()
        app.logger.exception('Unable to create shipment from orders')
        return jsonify({'error': 'Unable to create shipment.'}), 500
    finally:
        db.close()

@app.route('/api/shipments/<shipment_id>/cancel', methods=['POST'])
def cancel_shipment(shipment_id):
    db = get_db()
    try:
        shipment = db.query(Shipment).filter(Shipment.id == shipment_id).with_for_update().first()
        if not shipment:
            return jsonify({'error': 'Shipment not found'}), 404
        if shipment.status not in {'Confirmed', 'Scheduled'}:
            return jsonify({'error': 'A shipment can only be cancelled before it enters transit.'}), 409

        items = db.query(ShipmentItem).filter(
            ShipmentItem.shipment_id == shipment_id,
            ShipmentItem.status.notin_(['cancelled', 'released', 'delivered']),
        ).with_for_update().all()
        if not items:
            return jsonify({'error': 'This shipment has no active manifest. Reconcile its legacy cargo before changing it.'}), 409

        current_status = shipment.status
        cancelled = db.execute(
            update(Shipment)
            .where(Shipment.id == shipment_id, Shipment.status == current_status)
            .values(status='Cancelled', current_payload_kg=0.0)
        )
        if cancelled.rowcount != 1:
            db.rollback()
            return jsonify({'error': 'Shipment status changed. Refresh and try again.'}), 409

        for item in items:
            if item.status in {'cancelled', 'released', 'delivered'}:
                continue
            if item.order_id:
                order = db.query(Order).filter(Order.id == item.order_id).with_for_update().first()
                if order and order.shipment_id == shipment_id:
                    order.shipment_id = None
                    if order.stage not in {'Cancelled', 'Delivered'}:
                        order.stage = 'Packed'
                    order.is_disrupted = False
                item.status = 'cancelled'
            else:
                if item.listing_id and not release_listing_inventory(db, item.listing_id, item.quantity):
                    db.rollback()
                    return jsonify({'error': 'Could not release reserved produce. No shipment changes were saved.'}), 409
                item.status = 'released'

        for stop in shipment.stops:
            stop.status = 'Cancelled'

        log_audit(db, 'SHIPMENT_CANCELLED', 'SHIPMENT', shipment_id,
                  details={'releasedListingItems': sum(1 for item in items if item.order_id is None)})
        db.commit()
        return jsonify({'success': True, 'shipment': shipment.to_dict()})
    except Exception:
        db.rollback()
        app.logger.exception('Unable to cancel shipment %s', shipment_id)
        return jsonify({'error': 'Unable to cancel shipment.'}), 500
    finally:
        db.close()


@app.route('/api/shipments/<shipment_id>/stage', methods=['PATCH'])
def advance_shipment_stage(shipment_id):
    db = get_db()
    try:
        shipment = db.query(Shipment).filter(Shipment.id == shipment_id).with_for_update().first()
        if not shipment:
            return jsonify({'error': 'Shipment not found'}), 404

        data = request.get_json(silent=True)
        if data is None and request.get_data(cache=True).strip():
            return jsonify({'error': 'Request body must be valid JSON.'}), 400
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return jsonify({'error': 'A JSON object is required.'}), 400
        new_status = data.get('status')
        allowed_transitions = {
            'Draft': {'Confirmed'},
            'Confirmed': {'Scheduled'},
            'Scheduled': {'In Transit'},
            'In Transit': {'Delivered', 'Disrupted'},
            'Disrupted': {'In Transit'},
            'Delivered': set(),
            'Cancelled': set(),
        }
        current_status = shipment.status
        possible = allowed_transitions.get(current_status)
        if possible is None:
            return jsonify({'error': f'Unknown current shipment status: {current_status}'}), 409
        if not possible:
            return jsonify({'error': f'Shipment cannot move from {current_status}.'}), 409

        if new_status is None:
            if len(possible) != 1:
                return jsonify({'error': 'Choose the next shipment status explicitly.'}), 400
            new_status = next(iter(possible))
        if not isinstance(new_status, str) or new_status not in possible:
            return jsonify({'error': f'Invalid shipment transition from {current_status} to {new_status}.'}), 409

        items = db.query(ShipmentItem).filter(ShipmentItem.shipment_id == shipment_id).with_for_update().all()
        active_items = [item for item in items if item.status not in {'cancelled', 'released', 'delivered'}]
        if new_status in {'Scheduled', 'In Transit', 'Delivered'} and not active_items:
            return jsonify({'error': 'A shipment must contain active manifest items before it can move.'}), 409
        if new_status == 'Delivered':
            open_events = db.query(DisruptionEvent.id).filter(
                DisruptionEvent.shipment_id == shipment_id,
                DisruptionEvent.event_type == 'route_block',
                DisruptionEvent.status == 'open',
            ).first()
            if open_events:
                return jsonify({'error': 'Resolve or resume all open shipment disruptions before marking delivery complete.'}), 409

        shipment_values = {'status': new_status}
        if new_status == 'Delivered':
            shipment_values['current_payload_kg'] = 0.0
        transition = db.execute(
            update(Shipment)
            .where(Shipment.id == shipment_id, Shipment.status == current_status)
            .values(**shipment_values)
        )
        if transition.rowcount != 1:
            db.rollback()
            return jsonify({'error': 'Shipment status changed. Refresh and try again.'}), 409
        db.refresh(shipment)

        now = datetime.now(timezone.utc)
        order_ids = []
        for item in active_items:
            if new_status == 'Scheduled':
                item.status = 'scheduled'
            elif new_status == 'In Transit':
                item.status = 'in_transit'
            elif new_status == 'Disrupted':
                item.status = 'disrupted'
            elif new_status == 'Delivered':
                item.status = 'delivered'

            order = db.query(Order).filter(Order.id == item.order_id).first() if item.order_id else None
            if not order:
                continue
            order_ids.append(order.id)
            if new_status == 'In Transit':
                order.stage = 'In Transit'
                order.is_disrupted = False
                order.disruption_reason = None
            elif new_status == 'Disrupted':
                order.is_disrupted = True
                order.disruption_reason = f'Shipment {shipment_id} is disrupted.'
                already_open = db.query(DisruptionEvent.id).filter(
                    DisruptionEvent.order_id == order.id,
                    DisruptionEvent.shipment_id == shipment_id,
                    DisruptionEvent.status == 'open',
                ).first()
                if not already_open:
                    db.add(DisruptionEvent(
                        id=new_record_id('DISR'),
                        order_id=order.id,
                        shipment_id=shipment_id,
                        event_type='route_block',
                        severity='high',
                        description=f'Shipment {shipment_id} was reported disrupted while carrying order {order.id}.',
                        affected_crop=order.product_name,
                        affected_quantity=order.quantity,
                        original_buyer_id=order.buyer_id,
                        status='open',
                        created_at=now,
                    ))
            elif new_status == 'Delivered':
                order.stage = 'Delivered'
                order.is_disrupted = False
                order.disruption_reason = None
                db.add(Notification(
                    id=new_record_id('notif'),
                    user_id=order.buyer_id,
                    role='buyer',
                    title=f'Order delivered: {order.id}',
                    message=f'{order.quantity:g} {order.unit} of {order.product_name} was delivered.',
                    tone='success',
                    link='/buyer/orders',
                    created_at=now,
                ))
                db.add(Notification(
                    id=new_record_id('notif'),
                    user_id=order.farmer_id,
                    role='farmer',
                    title=f'Order delivered: {order.id}',
                    message=f'{order.quantity:g} {order.unit} of {order.product_name} was delivered to {order.buyer_name}.',
                    tone='success',
                    link='/farmer/orders',
                    created_at=now,
                ))

        if new_status == 'Disrupted':
            pooled_lines = [item for item in active_items if not item.order_id]
            if pooled_lines and not db.query(DisruptionEvent.id).filter(
                DisruptionEvent.shipment_id == shipment_id,
                DisruptionEvent.order_id.is_(None),
                DisruptionEvent.status == 'open',
            ).first():
                db.add(DisruptionEvent(
                    id=new_record_id('DISR'),
                    shipment_id=shipment_id,
                    event_type='route_block',
                    severity='high',
                    description=f'Shipment {shipment_id} carrying pooled produce was reported disrupted.',
                    affected_crop='Pooled produce',
                    affected_quantity=sum(item.quantity for item in pooled_lines),
                    status='open',
                    created_at=now,
                ))

        if current_status == 'Disrupted' and new_status == 'In Transit':
            for event in db.query(DisruptionEvent).filter(
                DisruptionEvent.shipment_id == shipment_id,
                DisruptionEvent.event_type == 'route_block',
                DisruptionEvent.status == 'open',
            ).all():
                event.status = 'resolved'
                event.resolved_at = now
                event.recovery_notes = 'Shipment resumed by the logistics coordinator.'

        stop_status = {
            'Scheduled': 'Scheduled',
            'In Transit': None,
            'Disrupted': 'Disrupted',
            'Delivered': 'Delivered',
        }.get(new_status)
        for stop in shipment.stops:
            if new_status == 'In Transit':
                stop.status = 'Picked Up' if stop.stop_type == 'pickup' else 'In Transit'
            elif stop_status:
                stop.status = stop_status

        log_audit(db, 'SHIPMENT_STATUS_UPDATED', 'SHIPMENT', shipment_id,
                  details={'from': current_status, 'to': new_status, 'orderIds': order_ids})
        db.commit()
        return jsonify({'success': True, 'shipment': shipment.to_dict()})
    except Exception:
        db.rollback()
        app.logger.exception('Unable to advance shipment %s', shipment_id)
        return jsonify({'error': 'Unable to update shipment status.'}), 500
    finally:
        db.close()

# ----------------- OPERATIONAL ANALYTICS -----------------
@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    db = get_db()
    try:
        listings = db.query(ProduceListing).filter(ProduceListing.is_active == True).all()
        active_listings_count = len(listings)
        total_available_kg = sum(l.available_quantity for l in listings)

        orders = db.query(Order).all()
        total_orders_count = len(orders)
        fulfilled_orders = len([o for o in orders if o.stage == 'Delivered'])
        active_orders = len([o for o in orders if o.stage not in ['Delivered', 'Cancelled']])
        total_gross_volume_inr = sum(o.total for o in orders if o.stage != 'Cancelled')

        shipments = db.query(Shipment).all()
        active_shipments_count = len([s for s in shipments if s.status not in {'Delivered', 'Cancelled'}])
        shipment_items = db.query(ShipmentItem).filter(
            ShipmentItem.status.notin_(['cancelled', 'released'])
        ).all()
        total_pooled_kg = sum(item.quantity for item in shipment_items if item.unit == 'kg')
        total_logistics_savings_inr = sum(
            s.estimated_savings for s in shipments if s.status != 'Cancelled'
        )

        disruptions = db.query(DisruptionEvent).all()
        open_disruptions_count = len([d for d in disruptions if d.status == 'open'])
        recovered_disruptions_count = len([d for d in disruptions if d.status == 'resolved'])

        # Dynamic volume by crop from actual orders
        crop_volumes = {}
        for o in orders:
            crop_volumes[o.product_name] = crop_volumes.get(o.product_name, 0.0) + o.quantity

        top_crops = [
            {'name': crop, 'volume': round(vol, 1)}
            for crop, vol in sorted(crop_volumes.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        # Category breakdown from active listings
        cat_counts = {}
        for l in listings:
            cat_counts[l.category] = cat_counts.get(l.category, 0) + 1

        category_split = [
            {'name': cat, 'value': count}
            for cat, count in cat_counts.items()
        ]

        return jsonify({
            'metrics': {
                'activeListingsCount': active_listings_count,
                'totalAvailableKg': round(total_available_kg, 1),
                'totalOrdersCount': total_orders_count,
                'activeOrdersCount': active_orders,
                'fulfilledOrdersCount': fulfilled_orders,
                'totalGrossVolumeINR': round(total_gross_volume_inr, 2),
                'activeShipmentsCount': active_shipments_count,
                'totalPooledKg': round(total_pooled_kg, 1),
                'totalLogisticsSavingsINR': round(total_logistics_savings_inr, 2),
                'openDisruptionsCount': open_disruptions_count,
                'recoveredDisruptionsCount': recovered_disruptions_count,
            },
            'topCrops': top_crops,
            'categorySplit': category_split,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    finally:
        db.close()

# ----------------- SAP ENTERPRISE GATEWAY -----------------
@app.route('/api/sap/status', methods=['GET'])
def sap_status():
    return jsonify({
        'status': 'READY_FOR_RFC_ODATA',
        'gateway': 'FarmLink AI — SAP S/4HANA & SAP TM Integration Bridge',
        'protocolsSupported': ['OData v4', 'RFC BAPI', 'cXML', 'REST Webhooks'],
        'connectedAdapters': [
            {'system': 'SAP S/4HANA Sourcing & Procurement (MM)', 'api': 'API_PURCHASEORDER_PROCESS_SRV', 'entity': 'A_PurchaseOrder'},
            {'system': 'SAP Transportation Management (SAP TM 9.6+)', 'api': 'FreightOrder_In', 'entity': 'FreightOrder'},
            {'system': 'SAP Supply Chain Control Tower', 'api': 'EventManagement_In', 'entity': 'DisruptionAlert'},
        ],
        'mockSimulation': True,
    })

@app.route('/api/sap/export-po/<order_id>', methods=['POST'])
def export_sap_po(order_id):
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        payload = sap_adapter.map_order_to_sap_purchase_order(order.to_dict())
        log_audit(db, 'SAP_PO_EXPORTED', 'ORDER', order_id, details={'sap_po': payload.get('PurchaseOrder')})
        db.commit()
        return jsonify({'success': True, 'sapPurchaseOrder': payload})
    finally:
        db.close()

@app.route('/api/sap/export-tm/<shipment_id>', methods=['POST'])
def export_sap_tm(shipment_id):
    db = get_db()
    try:
        shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
        if not shipment:
            return jsonify({'error': 'Shipment not found'}), 404
        payload = sap_adapter.map_shipment_to_sap_tm_freight_order(shipment.to_dict())
        log_audit(db, 'SAP_TM_EXPORTED', 'SHIPMENT', shipment_id, details={'sap_fo': payload.get('FreightOrderID')})
        db.commit()
        return jsonify({'success': True, 'sapFreightOrder': payload})
    finally:
        db.close()

@app.route('/api/sap/control-tower-alert/<disruption_id>', methods=['POST'])
def export_sap_disruption(disruption_id):
    db = get_db()
    try:
        disr = db.query(DisruptionEvent).filter(DisruptionEvent.id == disruption_id).first()
        if not disr:
            return jsonify({'error': 'Disruption not found'}), 404
        payload = sap_adapter.create_sap_control_tower_disruption_alert(disr.to_dict())
        log_audit(db, 'SAP_ALERT_DISPATCHED', 'DISRUPTION_EVENT', disruption_id, details={'alert_id': payload.get('AlertID')})
        db.commit()
        return jsonify({'success': True, 'sapControlTowerAlert': payload})
    finally:
        db.close()

# ----------------- NOTIFICATIONS & AUDIT -----------------
@app.route('/api/notifications', methods=['GET'])
def list_notifications():
    db = get_db()
    try:
        role = request.args.get('role')
        user_id = request.args.get('userId')
        q = db.query(Notification)
        if user_id:
            q = q.filter((Notification.user_id == user_id) | (Notification.user_id == None))
        if role:
            q = q.filter((Notification.role == role) | (Notification.role == None))
        notifs = q.order_by(desc(Notification.created_at)).limit(20).all()
        return jsonify({'notifications': [n.to_dict() for n in notifs]})
    finally:
        db.close()

@app.route('/api/notifications/<notif_id>/read', methods=['PATCH'])
def mark_notification_read(notif_id):
    db = get_db()
    try:
        n = db.query(Notification).filter(Notification.id == notif_id).first()
        if not n:
            return jsonify({'error': 'Notification not found'}), 404
        n.is_read = True
        db.commit()
        return jsonify({'success': True})
    except Exception:
        db.rollback()
        app.logger.exception('Unable to mark notification %s read', notif_id)
        return jsonify({'error': 'Unable to update notification.'}), 500
    finally:
        db.close()

@app.route('/api/audit-logs', methods=['GET'])
def list_audit_logs():
    db = get_db()
    try:
        logs = db.query(AuditLog).order_by(desc(AuditLog.created_at)).limit(50).all()
        return jsonify({'auditLogs': [l.to_dict() for l in logs]})
    finally:
        db.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('FARMLINK_HOST') or '127.0.0.1'
    print(f"FarmLink AI Flask backend starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
