from fastapi import FastAPI


# =========================
# ROUTERS IMPORTS
# =========================

from routers.products import router as products_router
from routers.orders import router as orders_router
from routers.forecast import router as forecast_router
from routers.wallet import router as wallet_router



# =========================
# APP INITIALIZATION
# =========================

app = FastAPI(

    title="Agri Market AI API",

    description=
    "AI powered agricultural marketplace, price forecasting and farmer payments",

    version="1.0.0"

)



# =========================
# MARKETPLACE ROUTERS
# =========================


# Farmer produce listings

app.include_router(

    products_router,

    prefix="/api/marketplace/products",

    tags=["Products"]

)



# Buyer orders

app.include_router(

    orders_router,

    prefix="/api/marketplace/orders",

    tags=["Orders"]

)



# AI price prediction

app.include_router(

    forecast_router,

    prefix="/api/marketplace/forecast",

    tags=["Forecast"]

)



# Farmer wallet and payments

app.include_router(

    wallet_router,

    prefix="/api/marketplace/wallet",

    tags=["Wallet"]

)



# =========================
# HEALTH CHECK
# =========================


@app.get("/")

def home():

    return {

        "message":
        "Agri Market AI Backend Running",

        "status":
        "healthy",

        "services":[

            "Products API",

            "Orders API",

            "AI Price Forecast",

            "Farmer Wallet"

        ]

    }
