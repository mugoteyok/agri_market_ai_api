from fastapi import FastAPI


# =====================================
# IMPORT ROUTERS
# =====================================

from routers.products import router as products_router
from routers.orders import router as orders_router
from routers.forecast import router as forecast_router
from routers.wallet import router as wallet_router



# =====================================
# CREATE FASTAPI APP
# =====================================

app = FastAPI(

    title="Agri Market AI API",

    description="AI powered agricultural marketplace, price forecasting and farmer payments",

    version="1.0.0"

)



# =====================================
# API ROUTERS
# Base URL:
/api/marketplace
# =====================================

app.include_router(

    products_router,

    prefix="/api/marketplace",

    tags=["Products"]

)



app.include_router(

    orders_router,

    prefix="/api/marketplace",

    tags=["Orders"]

)



app.include_router(

    forecast_router,

    prefix="/api/marketplace",

    tags=["Forecast"]

)



app.include_router(

    wallet_router,

    prefix="/api/marketplace",

    tags=["Wallet"]

)



# =====================================
# HEALTH CHECK
# =====================================

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

            "Farmer Wallet"

        ]

    }
