from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.api import router as api_router
from app.routes.pages import router as pages_router

app = FastAPI(title="sub2api-view")


@app.middleware("http")
async def allow_iframe_embedding(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors *"
    if "X-Frame-Options" in response.headers:
        del response.headers["X-Frame-Options"]
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(api_router)
app.include_router(pages_router)
