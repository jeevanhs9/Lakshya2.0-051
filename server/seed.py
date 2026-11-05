"""
FarmLink AI — Reproducible Database Seeder
Populates SQLite database with realistic agricultural records for Karnataka districts
(Kolar, Chikkaballapur, Tumakuru, Mandya, Bengaluru Urban).
"""

import os
import json
import sys
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from models import (
    Base, User, ProduceListing, Order, BuyerOffer, Shipment, ShipmentStop,
    ShipmentItem, DisruptionEvent, AuditLog, Notification
)

DB_PATH = os.path.join(os.path.dirname(__file__), 'farmlink.db')
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
DATABASE_URL = os.environ.get('FARMLINK_DATABASE_URL') or f'sqlite:///{DB_PATH}'
engine_options = {'pool_pre_ping': True}
if DATABASE_URL.startswith('sqlite:'):
    engine_options['connect_args'] = {'check_same_thread': False, 'timeout': 30}
engine = create_engine(DATABASE_URL, **engine_options)
Session = sessionmaker(bind=engine)


def metro_demo_buyer():
    return User(
        id='b8',
        name='Metro Wholesale Mandi Traders',
        email='procurement@metrowholesale.in',
        role='buyer',
        org_name='Metro Wholesale Mandi Traders',
        location='Yeshwanthpur APMC Yard, Bengaluru',
        phone='+91 80 1122 3344',
    )


def repair_demo_users():
    """Add demo buyers referenced by existing seeded offers without resetting data."""
    existing_tables = set(inspect(engine).get_table_names())
    if not {'users', 'buyer_offers'}.issubset(existing_tables):
        raise RuntimeError('Initialize the FarmLink database before applying demo data repairs.')

    session = Session()
    try:
        has_offer_for_b8 = session.query(BuyerOffer.id).filter(BuyerOffer.buyer_id == 'b8').first()
        if not has_offer_for_b8:
            print('No seeded offers reference buyer b8; no data changes were needed.')
            return

        existing_user = session.query(User).filter(User.id == 'b8').first()
        if existing_user:
            if existing_user.role != 'buyer':
                raise RuntimeError('User ID b8 is already assigned to a non-buyer account.')
            print('Demo buyer b8 is already present; no data changes were needed.')
            return

        email_owner = session.query(User).filter(User.email == 'procurement@metrowholesale.in').first()
        if email_owner:
            raise RuntimeError('The Metro demo buyer email is already assigned to another user ID.')

        session.add(metro_demo_buyer())
        session.commit()
        print('Added missing demo buyer b8. Existing listings, orders, offers, and other data were preserved.')
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def seed_database(reset=False):
    existing_tables = inspect(engine).get_table_names()
    if existing_tables and not reset:
        raise RuntimeError('Database already has tables. Pass --reset only if you intend to replace its data.')
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = Session()

    # 1. Users & Roles
    users = [
        User(
            id='f1',
            name='Ramesh Gowda',
            email='ramesh.fpo@farmlink.ai',
            role='farmer',
            org_name="Farmers' FPO, Kolar",
            location='Kolar, Karnataka',
            phone='+91 98450 12345',
            avatar='https://images.unsplash.com/photo-1595475207225-428b62bda831?q=80&w=200&auto=format&fit=crop',
        ),
        User(
            id='f2',
            name='Manjunath Byregowda',
            email='manjunath.fpo@farmlink.ai',
            role='fpo',
            org_name='Namma Raitha FPO Collective',
            location='Chikkaballapur, Karnataka',
            phone='+91 98450 67890',
            avatar='https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?q=80&w=200&auto=format&fit=crop',
        ),
        User(
            id='b1',
            name='ABC Hostel & Canteen',
            email='procurement@abchostel.in',
            role='buyer',
            org_name='ABC Hostel',
            location='Bengaluru Central, Karnataka',
            phone='+91 80 4567 8901',
            avatar='https://images.unsplash.com/photo-1568602471122-7832951cc4c5?q=80&w=200&auto=format&fit=crop',
        ),
        User(
            id='b2',
            name='GreenTable Restaurant Collective',
            email='chef@greentable.in',
            role='buyer',
            org_name='GreenTable Restaurants',
            location='Bengaluru East, Karnataka',
            phone='+91 80 9876 5432',
            avatar='https://images.unsplash.com/photo-1534528741775-53994a69daeb?q=80&w=200&auto=format&fit=crop',
        ),
        User(
            id='b3',
            name='FreshMart Retail Chain',
            email='sourcing@freshmart.in',
            role='buyer',
            org_name='FreshMart Retail',
            location='Bengaluru North, Karnataka',
            phone='+91 80 3344 5566',
            avatar='https://images.unsplash.com/photo-1500648767791-00dcc994a43e?q=80&w=200&auto=format&fit=crop',
        ),
        metro_demo_buyer(),
        User(
            id='l1',
            name='Suresh Patil',
            email='suresh.logistics@farmlink.ai',
            role='logistics',
            org_name='FarmLink Logistics Hub — Bengaluru',
            location='Bengaluru, Karnataka',
            phone='+91 99012 34567',
            avatar='https://images.unsplash.com/photo-1633332755192-727a05c4013d?q=80&w=200&auto=format&fit=crop',
        ),
        User(
            id='a1',
            name='Priya Sharma',
            email='admin@farmlink.ai',
            role='admin',
            org_name='FarmLink AI Platform Team',
            location='Bengaluru, Karnataka',
            phone='+91 80 1234 5678',
            avatar='https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?q=80&w=200&auto=format&fit=crop',
        ),
    ]
    session.add_all(users)

    # 2. Produce Listings
    listings = [
        ProduceListing(
            id='p1',
            farmer_id='f1',
            name='Tomato',
            category='Vegetables',
            quantity=1000.0,
            available_quantity=880.0,
            unit='kg',
            price=30.0,
            quality='Grade A',
            harvest_date='2026-10-18',
            location='Kolar, Karnataka',
            demand='High',
            image='https://images.unsplash.com/photo-1546094096-0df4bcaaa337?q=80&w=800&auto=format&fit=crop',
            description='Vine-ripened tomatoes grown by 40-member FPO in Kolar. Harvested within 24 hours, perfect for bulk institutional and HoReCa buyers.',
            is_active=True,
        ),
        ProduceListing(
            id='p2',
            farmer_id='f2',
            name='Onion',
            category='Vegetables',
            quantity=800.0,
            available_quantity=600.0,
            unit='kg',
            price=22.0,
            quality='Grade A',
            harvest_date='2026-10-15',
            location='Chikkaballapur, Karnataka',
            demand='Medium',
            image='https://images.unsplash.com/photo-1620574387735-3624d75b2dbc?q=80&w=800&auto=format&fit=crop',
            description='Medium-sized cured red onions ready for storage-grade transport. Sourced directly from local farmer collective.',
            is_active=True,
        ),
        ProduceListing(
            id='p3',
            farmer_id='f1',
            name='Potato',
            category='Vegetables',
            quantity=2000.0,
            available_quantity=1500.0,
            unit='kg',
            price=20.0,
            quality='Grade B',
            harvest_date='2026-10-14',
            location='Tumkur, Karnataka',
            demand='Medium',
            image='https://images.unsplash.com/photo-1518977676601-b53f82aba655?q=80&w=800&auto=format&fit=crop',
            description='Graded Jyoti variety potatoes, cleaned and sack-packed for wholesale distribution.',
            is_active=True,
        ),
        ProduceListing(
            id='p4',
            farmer_id='f2',
            name='Spinach',
            category='Vegetables',
            quantity=300.0,
            available_quantity=260.0,
            unit='kg',
            price=18.0,
            quality='Grade A',
            harvest_date='2026-10-19',
            location='Kolar, Karnataka',
            demand='High',
            image='https://images.unsplash.com/photo-1576045057995-568f588f82fb?q=80&w=800&auto=format&fit=crop',
            description='Freshly cut palak harvested early morning. Packed in perforated crates.',
            is_active=True,
        ),
        ProduceListing(
            id='p5',
            farmer_id='f1',
            name='Green Chilli',
            category='Vegetables',
            quantity=250.0,
            available_quantity=160.0,
            unit='kg',
            price=40.0,
            quality='Grade A',
            harvest_date='2026-10-18',
            location='Kolar, Karnataka',
            demand='High',
            image='https://images.unsplash.com/photo-1588252303782-cb80119abd6d?q=80&w=800&auto=format&fit=crop',
            description='Pungent G4 variety green chillies, sorted and packed in 10kg bags.',
            is_active=True,
        ),
        ProduceListing(
            id='p6',
            farmer_id='f2',
            name='Carrot',
            category='Vegetables',
            quantity=500.0,
            available_quantity=440.0,
            unit='kg',
            price=25.0,
            quality='Grade A',
            harvest_date='2026-10-17',
            location='Chikkaballapur, Karnataka',
            demand='Medium',
            image='https://images.unsplash.com/photo-1598170845058-32b9d6a5c317?q=80&w=800&auto=format&fit=crop',
            description='Crisp, sweet orange carrots, washed and graded.',
            is_active=True,
        ),
        ProduceListing(
            id='p7',
            farmer_id='f1',
            name='Rice (Sona Masoori)',
            category='Grains',
            quantity=3000.0,
            available_quantity=2700.0,
            unit='kg',
            price=42.0,
            quality='Grade A',
            harvest_date='2026-09-20',
            location='Mandya, Karnataka',
            demand='High',
            image='https://images.unsplash.com/photo-1586201375761-83865001e31c?q=80&w=800&auto=format&fit=crop',
            description='Premium aged Sona Masoori raw rice, single polished.',
            is_active=True,
        ),
    ]
    session.add_all(listings)

    # 3. Orders
    orders = [
        Order(
            id='ORD-1042',
            buyer_id='b1',
            buyer_name='ABC Hostel',
            farmer_id='f1',
            farmer_name="Farmers' FPO, Kolar",
            listing_id='p1',
            product_name='Tomato',
            quantity=120.0,
            unit='kg',
            subtotal=3600.0,
            logistics_fee=288.0,
            platform_fee=72.0,
            total=3960.0,
            payment_method='UPI',
            stage='In Transit',
            placed_on='2026-10-16',
            eta='2026-10-21',
            delivery_location='Vasanth Nagar, Bengaluru Central',
            shipment_id='SHP-101',
        ),
        Order(
            id='ORD-1041',
            buyer_id='b2',
            buyer_name='GreenTable Restaurants',
            farmer_id='f2',
            farmer_name='Namma Raitha FPO Collective',
            listing_id='p2',
            product_name='Onion',
            quantity=200.0,
            unit='kg',
            subtotal=4400.0,
            logistics_fee=352.0,
            platform_fee=88.0,
            total=4840.0,
            payment_method='Net Banking',
            stage='In Transit',
            placed_on='2026-10-17',
            eta='2026-10-21',
            delivery_location='Indiranagar, Bengaluru East',
            shipment_id='SHP-101',
        ),
        Order(
            id='ORD-1040',
            buyer_id='b3',
            buyer_name='FreshMart Retail',
            farmer_id='f1',
            farmer_name="Farmers' FPO, Kolar",
            listing_id='p3',
            product_name='Potato',
            quantity=500.0,
            unit='kg',
            subtotal=10000.0,
            logistics_fee=800.0,
            platform_fee=200.0,
            total=11000.0,
            payment_method='Bank Transfer',
            stage='In Transit',
            placed_on='2026-10-18',
            eta='2026-10-22',
            delivery_location='Hebbal, Bengaluru North',
            shipment_id='SHP-101',
        ),
        Order(
            id='ORD-1039',
            buyer_id='b1',
            buyer_name='ABC Hostel',
            farmer_id='f2',
            farmer_name='Namma Raitha FPO Collective',
            listing_id='p4',
            product_name='Spinach',
            quantity=40.0,
            unit='kg',
            subtotal=720.0,
            logistics_fee=58.0,
            platform_fee=14.0,
            total=792.0,
            payment_method='UPI',
            stage='In Transit',
            placed_on='2026-10-19',
            eta='2026-10-21',
            delivery_location='Vasanth Nagar, Bengaluru Central',
            shipment_id='SHP-101',
        ),
        # Seeded Disrupted Order for Scenario D Demonstration
        Order(
            id='ORD-1043',
            buyer_id='b1',
            buyer_name='ABC Hostel',
            farmer_id='f1',
            farmer_name="Farmers' FPO, Kolar",
            listing_id='p1',
            product_name='Tomato',
            quantity=180.0,
            unit='kg',
            subtotal=5400.0,
            logistics_fee=432.0,
            platform_fee=108.0,
            total=5940.0,
            payment_method='UPI',
            stage='Cancelled',
            placed_on='2026-10-19',
            eta='2026-10-21',
            delivery_location='Vasanth Nagar, Bengaluru Central',
            is_disrupted=True,
            disruption_reason='Buyer cancelled order due to kitchen equipment malfunction',
        ),
    ]
    session.add_all(orders)

    # 4. Buyer Offers (for Scenario B Offer Comparison)
    offers = [
        BuyerOffer(
            id='OFFER-201',
            listing_id='p1',
            buyer_id='b3',
            buyer_name='FreshMart Retail Chain',
            crop_name='Tomato',
            offered_price=30.0,
            requested_quantity=350.0,
            unit='kg',
            delivery_destination='Bengaluru North (Hebbal)',
            distance_km=56.0,
            transit_days=1,
            quality_requirement='Grade A',
            payment_terms='Immediate UPI (T+0)',
            status='pending',
        ),
        BuyerOffer(
            id='OFFER-202',
            listing_id='p1',
            buyer_id='b8',
            buyer_name='Metro Wholesale Mandi Traders',
            crop_name='Tomato',
            offered_price=32.0, # Higher gross price, but further away!
            requested_quantity=500.0,
            unit='kg',
            delivery_destination='Yeshwanthpur APMC Yard',
            distance_km=84.0, # Further distance -> higher freight deduction
            transit_days=2,
            quality_requirement='Grade A',
            payment_terms='Weekly Net-7',
            status='pending',
        ),
        BuyerOffer(
            id='OFFER-203',
            listing_id='p1',
            buyer_id='b2',
            buyer_name='GreenTable Restaurant Collective',
            crop_name='Tomato',
            offered_price=29.5,
            requested_quantity=200.0,
            unit='kg',
            delivery_destination='Bengaluru East (Indiranagar)',
            distance_km=62.0,
            transit_days=1,
            quality_requirement='Grade A',
            payment_terms='Immediate UPI (T+0)',
            status='pending',
        ),
    ]
    session.add_all(offers)

    # 5. Consolidated Shipment (Scenario A Load Pooling)
    shipment = Shipment(
        id='SHP-101',
        vehicle_id='KA-04-TR-1029',
        vehicle_name='Tata 407 (3.5T Reefer)',
        vehicle_capacity_kg=3500.0,
        current_payload_kg=860.0,
        status='In Transit',
        origin='Kolar FPO Hub',
        destination='Bengaluru Urban Delivery Corridor',
        planned_distance_km=128.0,
        planned_duration_hours=4.5,
        baseline_cost=4800.0,
        optimized_cost=3450.0,
        estimated_savings=1350.0,
        savings_pct=28.1,
        pooled_orders_count=4,
        explanation='Consolidates 4 packed buyer orders across Kolar, Chikkaballapur, and Tumakuru into a single 3.5T vehicle run serving 3 delivery nodes in Bengaluru.',
    )
    session.add(shipment)
    session.flush()

    seeded_shipment_orders = session.query(Order).filter(
        Order.shipment_id == shipment.id,
        Order.stage != 'Cancelled',
    ).all()
    session.add_all([
        ShipmentItem(
            id=f'SI-{order.id}',
            shipment_id=shipment.id,
            listing_id=order.listing_id,
            order_id=order.id,
            quantity=order.quantity,
            unit=order.unit,
            status='in_transit',
        )
        for order in seeded_shipment_orders
    ])

    stops = [
        ShipmentStop(
            id='stop-1',
            shipment_id=shipment.id,
            sequence=1,
            stop_type='pickup',
            name='Kolar FPO Collection Hub',
            location='Kolar, Karnataka',
            lat=13.1358,
            lng=78.1326,
            order_ids_json=json.dumps(['ORD-1042', 'ORD-1039']),
            eta='08:15 AM',
            status='Picked Up',
        ),
        ShipmentStop(
            id='stop-2',
            shipment_id=shipment.id,
            sequence=2,
            stop_type='pickup',
            name='Chikkaballapur Raitha Center',
            location='Chikkaballapur, Karnataka',
            lat=13.4350,
            lng=77.7315,
            order_ids_json=json.dumps(['ORD-1041']),
            eta='10:00 AM',
            status='Picked Up',
        ),
        ShipmentStop(
            id='stop-3',
            shipment_id=shipment.id,
            sequence=3,
            stop_type='pickup',
            name='Tumakuru Produce Mandi',
            location='Tumakuru, Karnataka',
            lat=13.3409,
            lng=77.1010,
            order_ids_json=json.dumps(['ORD-1040']),
            eta='12:15 PM',
            status='Picked Up',
        ),
        ShipmentStop(
            id='stop-4',
            shipment_id=shipment.id,
            sequence=4,
            stop_type='delivery',
            name='Bengaluru North Distribution Node (Hebbal)',
            location='Hebbal, Bengaluru',
            lat=13.0358,
            lng=77.5970,
            order_ids_json=json.dumps(['ORD-1040']),
            eta='03:10 PM',
            status='In Transit',
        ),
        ShipmentStop(
            id='stop-5',
            shipment_id=shipment.id,
            sequence=5,
            stop_type='delivery',
            name='Bengaluru Central Institutional Node',
            location='Vasanth Nagar, Bengaluru',
            lat=12.9860,
            lng=77.5940,
            order_ids_json=json.dumps(['ORD-1042', 'ORD-1039']),
            eta='04:00 PM',
            status='Upcoming',
        ),
        ShipmentStop(
            id='stop-6',
            shipment_id=shipment.id,
            sequence=6,
            stop_type='delivery',
            name='Bengaluru East HoReCa Cluster (Indiranagar)',
            location='Indiranagar, Bengaluru',
            lat=12.9784,
            lng=77.6408,
            order_ids_json=json.dumps(['ORD-1041']),
            eta='05:15 PM',
            status='Upcoming',
        ),
    ]
    session.add_all(stops)

    # 6. Disruption Event (Scenario D)
    disruption = DisruptionEvent(
        id='DISR-001',
        order_id='ORD-1043',
        event_type='cancellation',
        severity='high',
        description='ABC Hostel cancelled order for 180kg Grade A Tomatoes due to urgent institutional kitchen closure. Harvest is already packed at Kolar FPO.',
        affected_crop='Tomato',
        affected_quantity=180.0,
        original_buyer_id='b1',
        status='open',
    )
    session.add(disruption)

    # 7. Notifications
    notifs = [
        Notification(
            id='n1',
            user_id='f1',
            role='farmer',
            title='Disruption Alert: Order ORD-1043 Cancelled',
            message='ABC Hostel cancelled 180 kg Tomato order. FarmLink AI has identified 3 alternative buyers ready for immediate pickup.',
            tone='error',
            link='/disruptions',
        ),
        Notification(
            id='n2',
            user_id='f1',
            role='farmer',
            title='New Buyer Bid Received',
            message='FreshMart Retail placed an offer of ₹30/kg for 350 kg Tomatoes. Compare net proceeds now.',
            tone='info',
            link='/farmer/offers',
        ),
        Notification(
            id='n3',
            user_id='l1',
            role='logistics',
            title='Consolidated Run SHP-101 In Transit',
            message='Vehicle KA-04-TR-1029 has completed Kolar, Chikkaballapur, and Tumakuru pickups (860 kg loaded). Next stop: Hebbal.',
            tone='success',
            link='/logistics',
        ),
    ]
    session.add_all(notifs)

    # 8. Audit Log
    logs = [
        AuditLog(
            actor_id='sys',
            actor_role='system',
            action='DATABASE_SEEDED',
            entity_type='SYSTEM',
            entity_id='BOOTSTRAP',
            details=json.dumps({'status': 'seeded', 'records': 'users, listings, orders, offers, shipments'}),
        ),
        AuditLog(
            actor_id='b1',
            actor_role='buyer',
            action='ORDER_CANCELLED',
            entity_type='ORDER',
            entity_id='ORD-1043',
            details=json.dumps({'reason': 'Kitchen facility maintenance', 'quantity_kg': 180.0, 'crop': 'Tomato'}),
        ),
    ]
    session.add_all(logs)

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print("FarmLink AI database seeded successfully.")

if __name__ == '__main__':
    arguments = sys.argv[1:]
    if arguments == ['--repair-demo-users']:
        repair_demo_users()
    elif arguments in ([], ['--reset']):
        seed_database(reset='--reset' in arguments)
    else:
        raise SystemExit('Usage: python seed.py [--reset | --repair-demo-users]')
