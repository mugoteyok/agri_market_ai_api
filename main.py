from fastapi import FastAPI


from routers.products import router as products_router
from routers.orders import router as orders_router
from routers.forecast import router as forecast_router
from routers.wallet import router as wallet_router



app = FastAPI(
    title="Agri Market AI API",
    version="1.0.0"
)



app.include_router(
    products_router,
    prefix="/api/products",
    tags=["Products"]
)


app.include_router(
    orders_router,
    prefix="/api/orders",
    tags=["Orders"]
)


app.include_router(
    forecast_router,
    prefix="/api/forecast",
    tags=["Forecast"]
)


app.include_router(
    wallet_router,
    prefix="/api/wallet",
    tags=["Wallet"]
)



@app.get("/")
def home():

    return {
        "message":
        "Agri Market AI Backend Running",
        "status":
        "healthy"
    }
