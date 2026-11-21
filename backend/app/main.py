"""FastAPI 应用入口。"""

from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import run_migrations
from .routers import cities, images, items, metrics, outfits, recommend, weather

# Windows 注册表里常常没有 webp 映射，显式补上
mimetypes.add_type("image/webp", ".webp")

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings.ensure_dirs()
    run_migrations()
    settings.clear_tmp()
    yield


app = FastAPI(title="电子衣柜 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(items.router, prefix="/api/items", tags=["items"])
app.include_router(images.router, prefix="/api/images", tags=["images"])
app.include_router(weather.router, prefix="/api/weather", tags=["weather"])
app.include_router(recommend.router, prefix="/api/recommend", tags=["recommend"])
app.include_router(outfits.router, prefix="/api/outfits", tags=["outfits"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(cities.router, prefix="/api/cities", tags=["cities"])
app.mount("/media", StaticFiles(directory=settings.media_dir, check_dir=False), name="media")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
