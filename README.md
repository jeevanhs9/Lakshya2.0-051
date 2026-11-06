# FarmLink AI

FarmLink AI is a full-stack agricultural supply-chain prototype for farmers, FPOs, buyers, logistics operators, and platform administrators. It connects produce listings, buyer orders, shared-load shipments, delivery tracking, disruption recovery, route planning, and SAP-style enterprise exports in one role-based web application.

> Prototype scope: no real money moves through the platform. Checkout includes a clearly labelled local demo-payment flow only.

## Contents

- [Capabilities](#capabilities)
- [Technology stack](#technology-stack)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Architecture and data flow](#architecture-and-data-flow)
- [Database](#database)
- [Frontend and roles](#frontend-and-roles)
- [Internationalization](#internationalization)
- [Demo payment](#demo-payment)
- [REST API reference](#rest-api-reference)
- [Routing, maps, and GPS](#routing-maps-and-gps)
- [SAP gateway](#sap-gateway)
- [Tests and checks](#tests-and-checks)
- [Known prototype limits](#known-prototype-limits)

## Capabilities

- Role-based farmer/FPO, buyer, logistics, and administrator workspaces.
- Produce listing inventory with available-quantity reservations and updates.
- Buyer marketplace, cart, order creation, cancellation, and delivery stages.
- Demo checkout with a simulated payment approval and local reference number.
- Buyer-offer comparison using freight, platform fees, and net proceeds.
- Load pooling and shipment manifests that synchronise orders, listing inventory, stops, and delivery status.
- Shipment lifecycle management, cancellation handling, persisted location events, and live-device GPS ingestion.
- Map route display with configurable Google Maps browser integration; server-side geocoding/routing using Geoapify or Google Maps APIs when configured.
- Demand forecasting, supply-demand gaps, price intelligence, disruption recovery, platform analytics, notifications, and audit logs.
- SAP-style export adapters for purchase orders, transport orders, and disruption alerts.
- Language selector with English plus 12 Indian regional languages; the selected locale persists in local storage and Urdu enables RTL direction.

## Technology stack

| Area | Technologies | Purpose |
| --- | --- | --- |
| Frontend | React 19, Vite 8, React Router 7 | Single-page role-based application and route handling |
| UI | Tailwind CSS 4, Lucide React, Recharts | Responsive UI, icons, dashboards, and charts |
| Internationalization | i18next, react-i18next, i18next-browser-languagedetector | Persistent language selection, localized keys, English fallback |
| Backend | Python 3.10+, Flask 3, Flask-CORS | JSON REST API under `/api` |
| ORM | SQLAlchemy 2 | Database models, relationships, and portable database access |
| Database | PostgreSQL 18 recommended; SQLite included | Persistent application data and zero-setup demo mode |
| PostgreSQL driver | psycopg 3 | PostgreSQL SQLAlchemy connectivity |
| Maps and routing | Google Maps JavaScript API; Geoapify or Google server APIs | Browser map, address geocoding, and route calculations |
| Enterprise integration | SAP-style adapter layer | Mock S/4HANA MM, SAP TM, and Control Tower export payloads |
| Tests and code quality | pytest, oxlint, Vite build | Backend tests, frontend linting, production build checks |

## Quick start

### Prerequisites

- Node.js 20.19+ or 22.12+
- Python 3.10+
- PostgreSQL 18+ only when using PostgreSQL instead of the included SQLite demo database

### 1. Start the frontend

```powershell
cd "E:\farmlink-ai - Copy"
npm install
npm run dev
```

Open `http://localhost:5173`.

### 2. Start the backend

Open a second terminal:

```powershell
cd "E:\farmlink-ai - Copy\server"
pip install -r requirements.txt
python app.py
```

The API starts at `http://127.0.0.1:5000`. Vite proxies `/api/*` requests to that address during development.

### 3. First-run data preparation

The included SQLite database at `server/farmlink.db` contains demo data. If you are using an existing database from an earlier version, run the additive migrations once:

```powershell
cd "E:\farmlink-ai - Copy\server"
python migrate_shipment_items.py
python migrate_shipment_locations.py
python seed.py --repair-demo-users
```

`seed.py --reset` intentionally deletes the local demo database and recreates it. Do not run it when you need to preserve records.

## Configuration

Copy `.env.example` to `.env` at the repository root and set only the variables required by your environment. Never commit `.env` or publish API keys.

```env
# Frontend: empty means Vite's local /api proxy
VITE_API_BASE_URL=

# Database: empty uses server/farmlink.db
FARMLINK_DATABASE_URL=postgresql+psycopg://username:password@127.0.0.1:5432/farmlink

# Backend network configuration
FARMLINK_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
FARMLINK_HOST=127.0.0.1
PORT=5000

# Optional browser map integration; this is a browser-restricted key.
VITE_GOOGLE_MAPS_API_KEY=
VITE_GOOGLE_MAPS_MAP_ID=

# Optional server-only geocoding/routing provider. Do not expose either in Vite.
GOOGLE_MAPS_SERVER_API_KEY=
GEOAPIFY_API_KEY=
FARMLINK_GEOCODE_REGION=in
```

### Maps key separation

`VITE_GOOGLE_MAPS_API_KEY` is intentionally browser-visible and must be restricted by HTTP referrer and API. `GOOGLE_MAPS_SERVER_API_KEY` and `GEOAPIFY_API_KEY` are server-only secrets. Do not prefix server keys with `VITE_`.

## Architecture and data flow

```text
┌────────────────────────────────────────────────────────────────────┐
│ React + Vite client                                                 │
│ Roles · dashboards · cart · checkout · multilingual UI · maps      │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ /api/* JSON
┌──────────────────────────────▼─────────────────────────────────────┐
│ Flask API                                                           │
│ Auth demo · listings · orders · offers · pooling · shipments        │
│ forecasting · disruptions · analytics · notifications · SAP exports │
└───────────────┬───────────────────────────┬────────────────────────┘
                │ SQLAlchemy                │ optional HTTPS services
┌───────────────▼───────────────┐   ┌───────▼───────────────────────┐
│ PostgreSQL or SQLite           │   │ Geoapify / Google Maps APIs   │
│ relational operational data    │   │ geocoding and driving routes  │
└───────────────────────────────┘   └───────────────────────────────┘
```

### Order-to-delivery lifecycle

1. A farmer/FPO creates a `ProduceListing` with a current available quantity.
2. A buyer adds listings to the cart and completes the simulated checkout.
3. `POST /api/orders` creates order records and reserves/decrements listing inventory.
4. Pooling or shipment creation groups orders into a `Shipment`, `ShipmentItem` manifest, and ordered `ShipmentStop` records.
5. Shipment status changes update associated order stages. Shipment cancellation releases eligible reserved inventory and synchronises order state.
6. A logistics device can post coordinates to the shipment location endpoint. The frontend uses saved stops/manifest data for its map; visual vehicle movement is not a substitute for device GPS.
7. Delays, cancellations, or failures can create a `DisruptionEvent`; matching proposes alternative buyers and writes an audit record when a recovery is authorised.

## Database

### Database selection

The backend reads `FARMLINK_DATABASE_URL`.

- **Unset:** SQLite at `server/farmlink.db`; useful for local demos.
- **PostgreSQL URL:** PostgreSQL is used through SQLAlchemy and psycopg; recommended for concurrent or persistent deployment.

For a safe one-time transfer from SQLite to an empty PostgreSQL database:

```powershell
cd "E:\farmlink-ai - Copy\server"
python migrate_sqlite_to_postgres.py
```

The migration creates the schema, copies tables in foreign-key order, advances PostgreSQL integer sequences, and refuses to write into a PostgreSQL database that already contains FarmLink records.

### Core tables

| Table | Purpose |
| --- | --- |
| `users` | Farmer/FPO, buyer, logistics, and admin profiles |
| `produce_listings` | Produce lots, prices, quality, location, and current available quantity |
| `orders` | Buyer order financials, payment method, delivery address, stage, shipment link, disruption state |
| `buyer_offers` | Buyer bid, requested quantity, freight inputs, and offer state |
| `shipments` | Vehicle, capacity, route/cost metrics, status, and pooled-order summary |
| `shipment_stops` | Ordered pickup and delivery stops, coordinate pairs, ETA, and stop state |
| `shipment_items` | Shipment manifest entries linked to a listing and/or order |
| `shipment_locations` | GPS/location updates with source, accuracy, event time, and receive time |
| `disruption_events` | Cancellations, delays, route blocks, match/recovery state, and resolution notes |
| `audit_logs` | Action history for pooling, shipment, order, and disruption events |
| `notifications` | Role/user notifications, links, tone, and read state |

### Inventory integrity

`ProduceListing.available_quantity` is the quantity currently available to buy. Order and shipment operations validate quantities before changing inventory. `shipment_items` uses constraints to require a valid source and positive quantity; one shipment cannot have duplicate manifest entries for the same order.

## Frontend and roles

| Role | Main routes | Main responsibilities |
| --- | --- | --- |
| Farmer / FPO | `/farmer/*` | Listings, forecasts, buyer offers, pooling, orders, profile |
| Buyer | `/buyer/*` | Marketplace, product details, cart, simulated checkout, orders, profile |
| Logistics | `/logistics/*` | Shipment overview, route details, map, vehicle and delivery updates |
| Admin | `/admin/*` | Directories, platform orders, analytics, SAP gateway |
| Shared | `/disruptions` | Disruption matching and recovery workflow |

The frontend has a unified service layer in `src/services/api.js`. Read requests can display local seed data when the API is unavailable; actions that change data must receive a backend response before the UI treats them as saved.

## Internationalization

FarmLink supports 13 selectable locales:

| Code | Language | Direction |
| --- | --- | --- |
| `en` | English | LTR |
| `kn` | Kannada | LTR |
| `hi` | Hindi | LTR |
| `te` | Telugu | LTR |
| `ta` | Tamil | LTR |
| `ml` | Malayalam | LTR |
| `mr` | Marathi | LTR |
| `bn` | Bengali | LTR |
| `gu` | Gujarati | LTR |
| `pa` | Punjabi | LTR |
| `or` | Odia | LTR |
| `as` | Assamese | LTR |
| `ur` | Urdu | RTL |

- Locale selection is stored in `localStorage` under `farmlink-language`.
- `i18next-browser-languagedetector` restores that locale after refresh.
- English is the safe runtime fallback when a regional phrase has not yet been manually localized.
- UI code should use `useTranslation()` and explicit `t('namespace.key')` calls; automatic DOM text replacement is intentionally not used because it can create mixed-language pages.
- Locale resources live under `src/i18n/locales/`.

Run the available checks:

```powershell
npm run i18n:check   # reports locale-key completeness and fallback usage
npm run i18n:audit   # reports candidate hardcoded UI text still needing keys
```

## Demo payment

Checkout presents a **Demo Payment Gateway** after a buyer reviews their order. It:

1. Shows the calculated total and selected payment method.
2. Displays a visible prototype warning.
3. Simulates a local approval delay.
4. Generates a local `DEMO-...` reference.
5. Creates the order only after the user chooses **Create Demo Order**.

It does **not** collect, persist, transmit, or charge real UPI, card, PIN, account, or payment data. Replacing it with a real gateway requires server-side payment-order creation, webhook signature verification, idempotency, PCI-aware handling, and a payment reconciliation model.

## REST API reference

Base URL: `http://127.0.0.1:5000/api` locally. All responses are JSON. Successful responses use resource-specific properties such as `product`, `products`, `orders`, or `shipment`; failures return `{ "error": "..." }` with an HTTP error status.

### Service and demo authentication

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | API/database health status |
| POST | `/auth/demo-login` | Start a demo session for a supplied role |
| GET | `/auth/me?userId={id}` | Fetch a demo user profile |

### Products and inventory

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/products?category=&farmerId=&q=` | Search active produce listings |
| GET | `/products/{productId}` | Retrieve one listing |
| POST | `/products` | Create a listing |
| PUT | `/products/{productId}` | Update permitted listing fields |
| DELETE | `/products/{productId}` | Deactivate a listing |

### Orders

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/orders?buyerId=&farmerId=&stage=` | List/filter orders |
| POST | `/orders` | Create one or more order items; validates and reserves inventory |
| PATCH | `/orders/{orderId}/stage` | Move an order to a permitted stage |
| POST | `/orders/{orderId}/cancel` | Cancel an order and synchronise applicable inventory/shipment state |

Example order request:

```json
{
  "buyerId": "b1",
  "deliveryLocation": "Indiranagar, Bengaluru 560038",
  "paymentMethod": "UPI",
  "items": [{ "productId": "p1", "quantity": 50 }]
}
```

### Pooling and offers

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/pooling/opportunities` | Calculate compatible load-pooling opportunities |
| POST | `/pooling/confirm` | Confirm a pooling decision and create/update shipment data |
| GET | `/offers?listingId=&status=` | List buyer offers |
| POST | `/offers/compare` | Calculate freight/platform-adjusted offer comparison |
| POST | `/offers/{offerId}/accept` | Accept an offer and persist its state |

### Disruptions and forecasting

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/disruptions?status=` | List disruption events |
| GET | `/disruptions/{disruptionId}/matches` | Score alternative-buyer matches |
| POST | `/disruptions/{disruptionId}/recover` | Authorise a recovery/reassignment |
| GET | `/forecasting?crop=&market=` | Get forecast and price-intelligence data |
| GET | `/forecasting/gaps` | Get supply-demand gap analysis |

### Geocoding, routing, and shipments

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/routing/geocode?address=` | Resolve a location to coordinates via configured provider or local catalog |
| POST | `/routing/route` | Calculate a driving route for coordinate stops |
| GET | `/shipments?status=` | List saved shipments, stops, and manifests |
| POST | `/shipments` | Create a shipment from selected orders/listings/stops |
| GET | `/shipments/{shipmentId}/location` | Retrieve the latest persisted location event |
| POST | `/shipments/{shipmentId}/location` | Save a device/browser GPS location update |
| POST | `/shipments/{shipmentId}/cancel` | Cancel shipment and synchronise saved manifest/order state |
| PATCH | `/shipments/{shipmentId}/stage` | Advance shipment stage and synchronise related orders |

Example GPS update:

```json
{
  "latitude": 12.9716,
  "longitude": 77.5946,
  "accuracyMeters": 12,
  "source": "browser_gps",
  "recordedAt": "2026-11-05T12:00:00Z"
}
```

### Analytics, SAP, notifications, and audit logs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/analytics` | Platform totals, categories, crop volumes, and operational metrics |
| GET | `/sap/status` | Mock SAP integration/service status |
| POST | `/sap/export-po/{orderId}` | Create mock S/4HANA MM purchase-order export payload |
| POST | `/sap/export-tm/{shipmentId}` | Create mock SAP TM freight-order export payload |
| POST | `/sap/control-tower-alert/{disruptionId}` | Create mock Control Tower disruption alert payload |
| GET | `/notifications?role=&userId=` | Retrieve notifications for a role/user |
| PATCH | `/notifications/{notificationId}/read` | Mark a notification read |
| GET | `/audit-logs?entityType=&entityId=` | Retrieve audit history |

## Routing, maps, and GPS

- The route map reads saved shipment stops and manifest data; it does not invent shipment stops from display-only fixtures.
- Without a provider key, a small local location catalogue supports the demo.
- With `GEOAPIFY_API_KEY`, Geoapify Geocoding and Routing are used server-side. It takes precedence when both server providers are configured.
- With `GOOGLE_MAPS_SERVER_API_KEY`, Google Geocoding and Directions APIs can be used server-side.
- With `VITE_GOOGLE_MAPS_API_KEY`, the browser can render Google Maps. A map ID is optional; the app has a fallback demo map configuration.
- A moving truck visual is a demo preview. Real tracking requires a driver/device to submit positions to `POST /api/shipments/{shipmentId}/location`.

## SAP gateway

`server/sap_adapter.py` is an integration boundary, not a live SAP connection. It produces inspectable mock payloads for:

- SAP S/4HANA Sourcing & Procurement / MM purchase orders.
- SAP Transportation Management freight orders.
- SAP Supply Chain Control Tower disruption events.

Production SAP connectivity requires approved network access, system-specific destinations, service credentials, certificate/security configuration, error/retry handling, and reconciliation procedures.

## Repository map

```text
farmlink-ai/
├── src/
│   ├── pages/                 Role-specific screens
│   ├── components/            Reusable UI, maps, charts, marketplace and orders
│   ├── context/               Application state and mutation orchestration
│   ├── services/api.js        Browser-to-Flask service layer
│   ├── i18n/                  Locale registry, resources, selector, audit utilities
│   └── data/                  Demo fixtures and chart data
├── server/
│   ├── app.py                 Flask API routes and business coordination
│   ├── models.py              SQLAlchemy data model
│   ├── *_engine.py            Forecasting, matching, pricing, and pooling logic
│   ├── routing_service.py     Provider-neutral routing/geocoding adapter
│   ├── sap_adapter.py         Mock enterprise export boundary
│   ├── seed.py                Demo data seeding/repair
│   ├── migrate_*.py           Additive and SQLite-to-PostgreSQL migrations
│   └── tests/                 pytest backend tests
├── scripts/                   Translation completeness and hardcoded-text audits
├── .env.example               Safe configuration template
└── package.json               Frontend scripts and dependencies
```

## Tests and checks

Run from the repository root:

```powershell
npm run lint
npm run build
npm run i18n:check
npm run i18n:audit
```

Run backend tests:

```powershell
cd "E:\farmlink-ai - Copy\server"
pytest tests/
```

## Known prototype limits

- Authentication is a demo role picker. Production needs password/OAuth flows, JWT/session management, server-enforced RBAC, rate limiting, and secure password storage.
- Demo payment is intentionally not a real payment integration.
- Some regional resources still rely on English fallback while human translations are completed; run `npm run i18n:check` to see exact gaps.
- Forecast metrics and price intelligence use demonstration inputs, not validated live agricultural data.
- A route preview is not proof of live GPS tracking; tracking needs a trusted device integration.
- SAP exports are mock payloads, not live SAP calls.
- Before deployment, add managed PostgreSQL backups, migrations, monitoring, health checks, structured logging, HTTPS, secret management, data-retention controls, and CI.

## License and acknowledgements

Built as a FarmLink AI prototype for agricultural supply-chain resilience. The project aligns with UN SDGs #2 Zero Hunger, #8 Decent Work, #12 Responsible Consumption, and #13 Climate Action.
