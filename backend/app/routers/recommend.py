"""推荐接口：薄壳，主体在 recommend_service。"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from .. import limits
from ..db import get_db
from ..recommend_service import build_recommendation
from ..schemas import RecommendOut

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=RecommendOut)
async def recommend(
    request: Request,
    response: Response,
    occasion: str | None = Query(default=None, description="casual / work / sport / formal"),
    city: str | None = Query(default=None, description="城市名，不传默认杭州"),
    mode: Literal["rules", "llm"] = Query(default="rules", description="rules 或 llm"),
    x_llm_key: str | None = Header(default=None, alias="X-LLM-Key"),
    db: Session = Depends(get_db),
) -> RecommendOut:
    client_key = limits.client_key(
        request.headers.get("X-Forwarded-For"),
        request.client.host if request.client else None,
    )

    result, remaining = await build_recommendation(
        db,
        city=city,
        occasion=occasion,
        mode=mode,
        llm_key=x_llm_key,
        client_key=client_key,
    )

    if remaining is not None:
        response.headers["X-RateLimit-Remaining"] = str(remaining)
    return result
