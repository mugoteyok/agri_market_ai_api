
from fastapi import FastAPI

from routers.products import router as products_router
from routers.orders import router as orders_router
from routers.forecast import router as forecast_router
from routers.wallet import router as wallet_router
from routers.promotions import router as promotions_router


app = FastAPI(
    title="Agri Market AI API",
    description=(
        "AI powered agricultural marketplace, "
        "price forecasting and farmer payments"
    ),
    version="1.0.0"
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
# HEALTH CHECK
# ============================================================

@app.get("/")
def home():

    return {

        "message":
            "Agri Market AI Backend Running",

        "status":
            "healthy",

        "services": [

            "Products API",

            "Orders API",

            "AI Price Forecast",

            "Farmer Wallet",

            "Product Promotions"

        ]

    }


# ============================================================
# MARKETPLACE HEALTH CHECK
# ============================================================

@app.get("/api/marketplace/health")
def marketplace_health():

    return {

        "service":
            "Agri Market AI Marketplace",

        "status":
            "running",

        "modules": {

            "products":
                "active",

            "orders":
                "active",

            "forecast":
                "active",

            "wallet":
                "active",

            "promotions":
                "active"

        }

    }

