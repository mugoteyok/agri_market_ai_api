
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.products import router as products_router
from routers.orders import router as orders_router
from routers.forecast import router as forecast_router
from routers.wallet import router as wallet_router
from routers.promotions import router as promotions_router
from routers.recommendations import router as recommendations_router
from routers.subscriptions import router as subscriptions_router
from routers.farm_intelligence import router as farm_intelligence_router
from routers.market_intelligence import router as market_intelligence_router
from routers.support import router as support_router
from routers.support_admin import router as support_admin_router


# ============================================================
# MTN MOBILE MONEY CALLBACK
#
# Receives asynchronous payment notifications from MTN.
#
# The callback uses the Agri AI Assist payment_external_id
# to identify the order/payment.
# ============================================================

from routers.mtn_callback import router as mtn_callback_router


app = FastAPI(
    title="Agri Market AI API",
    description=(
        "AI powered agricultural marketplace, "
        "price forecasting and farmer payments"
    ),
    version="1.0.0"
)


# ============================================================
# CORS
#
# Allows the local web support portal to communicate with
# the API from the browser.
#
# This does not change the existing Flutter/mobile API
# functionality.
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# MARKETPLACE ROUTERS
# ============================================================


# ============================================================
# PRODUCTS
# ============================================================

app.include_router(
    products_router,
    prefix="/api/marketplace",
    tags=["Products"]
)


# ============================================================
# ORDERS
# ============================================================

app.include_router(
    orders_router,
    prefix="/api/marketplace",
    tags=["Orders"]
)


# ============================================================
# PRICE FORECAST
# ============================================================

app.include_router(
    forecast_router,
    prefix="/api/marketplace",
    tags=["Forecast"]
)


# ============================================================
# WALLET
# ============================================================

app.include_router(
    wallet_router,
    prefix="/api/marketplace",
    tags=["Wallet"]
)


# ============================================================
# PROMOTIONS
#
# Supplier paid/promoted farm-supply listings
# ============================================================

app.include_router(
    promotions_router,
    prefix="/api/marketplace",
    tags=["Promotions"]
)


# ============================================================
# AI FARM SUPPLY RECOMMENDATIONS
#
# Disease diagnosis → crop → recommendations
# → relevant Farm Supplies
# ============================================================

app.include_router(
    recommendations_router,
    prefix="/api/marketplace",
    tags=["Recommendations"]
)


# ============================================================
# SUBSCRIPTIONS
#
# Basic:
#   Activated immediately through the free subscription flow.
#
# Pro / Premium:
#   Requires confirmed MTN Mobile Money payment before
#   the subscription becomes active.
# ============================================================

app.include_router(
    subscriptions_router,
    prefix="/api/marketplace",
    tags=["Subscriptions"]
)


# ============================================================
# FARM INTELLIGENCE
#
# Weather forecasting + agricultural decision support
#
# Endpoint:
#
# GET /api/farm-intelligence?region=Jinja
#
# This router is intentionally registered under /api
# rather than /api/marketplace because Farm Intelligence
# is a farmer intelligence/weather service, not a marketplace
# module.
# ============================================================

app.include_router(
    farm_intelligence_router,
    prefix="/api",
    tags=["Farm Intelligence"]
)


# ============================================================
# MARKET INTELLIGENCE
#
# AI-powered crop price analysis and recommendations
#
# Endpoint:
#
# GET /api/market-intelligence/{crop_slug}
#
# Example:
#
# GET /api/market-intelligence/maize
#     ?current_price=1500
#     &previous_price=1400
#     &trend=rising
#     &supply_pressure=low
#     &storage_risk=low
#     &min_price=1100
#     &max_price=1700
#
# This router is registered under /api rather than
# /api/marketplace because Market Intelligence is an
# agricultural decision-support service.
# ============================================================

app.include_router(
    market_intelligence_router,
    prefix="/api",
    tags=["Market Intelligence"]
)


# ============================================================
# MTN MOBILE MONEY CALLBACK
#
# MTN will call this endpoint asynchronously after the
# customer approves/rejects the Mobile Money request.
#
# IMPORTANT:
#
# This router is registered under /api rather than
# /api/marketplace.
#
# Therefore, if mtn_callback.py contains:
#
#     @router.post("/mtn/callback")
#
# the final endpoint becomes:
#
#     POST /api/mtn/callback
#
# ============================================================

app.include_router(
    mtn_callback_router,
    prefix="/api",
    tags=["MTN Callback"]
)


# ============================================================
# CUSTOMER SUPPORT
#
# Customer support for farmers, suppliers and
# agricultural businesses.
#
# Endpoints:
#
# GET  /api/support/categories
# POST /api/support/tickets
# GET  /api/support/tickets
# GET  /api/support/tickets/{ticket_id}
# POST /api/support/tickets/{ticket_id}/messages
#
# This router is intentionally separate from the marketplace.
# ============================================================

app.include_router(
    support_router,
    tags=["Customer Support"]
)


# ============================================================
# SUPPORT ADMINISTRATION
#
# Internal customer support administration portal.
#
# These endpoints are protected by support-agent
# authentication inside support_admin.py.
#
# Endpoints:
#
# GET    /api/support/admin/stats
# GET    /api/support/admin/tickets
# GET    /api/support/admin/tickets/{ticket_id}
# POST   /api/support/admin/tickets/{ticket_id}/messages
# PATCH  /api/support/admin/tickets/{ticket_id}
# GET    /api/support/admin/agents
#
# This router is intentionally separate from the
# customer support router.
# ============================================================

app.include_router(
    support_admin_router,
    tags=["Support Administration"]
)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
def home():

    return {
        "message": "Agri Market AI Backend Running",

        "status": "healthy",

        "services": [
            "Products API",
            "Orders API",
            "AI Price Forecast",
            "Farmer Wallet",
            "Product Promotions",
            "AI Farm Supply Recommendations",
            "Subscriptions",
            "Farm Intelligence",
            "Market Intelligence",
            "MTN Mobile Money Callback"
        ]
    }


# ============================================================
# MARKETPLACE HEALTH CHECK
# ============================================================

@app.get("/api/marketplace/health")
def marketplace_health():

    return {
        "service": "Agri Market AI Marketplace",

        "status": "running",

        "modules": {

            "products": "active",

            "orders": "active",

            "forecast": "active",

            "wallet": "active",

            "promotions": "active",

            "recommendations": "active",

            "subscriptions": "active",

            "farm_intelligence": "active",

            "market_intelligence": "active",

            "mtn_callback": "active"

        }

    }

