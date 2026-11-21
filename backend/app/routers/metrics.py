"""指标接口：把 llm_metrics 聚合成调用量 / 成功率 / 降级分布 / 延迟分位 / token 消耗。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LlmMetric
from ..schemas import LatencyOut, MetricsOut, TokensOut

router = APIRouter()


def _scalar(db: Session, stmt) -> int:  # noqa: ANN001
    return int(db.execute(stmt).scalar_one() or 0)


def _percentile(
    db: Session, cutoff: str, fraction: float, total: int, *, only_model_calls: bool = False
) -> int | None:
    """用 SQL 排序 + OFFSET 取分位，不把整表拉进内存。"""
    if total <= 0:
        return None
    offset = min(total - 1, max(0, int(total * fraction)))
    stmt = select(LlmMetric.latency_ms).where(LlmMetric.created_at >= cutoff)
    if only_model_calls:
        stmt = stmt.where(LlmMetric.attempts > 0)
    stmt = stmt.order_by(LlmMetric.latency_ms.asc()).limit(1).offset(offset)
    value = db.execute(stmt).scalar_one_or_none()
    return int(value) if value is not None else None


@router.get("", response_model=MetricsOut)
def get_metrics(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> MetricsOut:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    window = LlmMetric.created_at >= cutoff

    total = _scalar(db, select(func.count()).select_from(LlmMetric).where(window))
    llm_success = _scalar(
        db,
        select(func.count())
        .select_from(LlmMetric)
        .where(window, LlmMetric.source == "llm", LlmMetric.cached.is_(False)),
    )
    cache_hits = _scalar(
        db,
        select(func.count()).select_from(LlmMetric).where(window, LlmMetric.cached.is_(True)),
    )
    fallbacks = _scalar(
        db,
        select(func.count()).select_from(LlmMetric).where(window, LlmMetric.source == "rules"),
    )

    fallback_rows = db.execute(
        select(LlmMetric.fallback_reason, func.count())
        .where(window, LlmMetric.fallback_reason.is_not(None))
        .group_by(LlmMetric.fallback_reason)
    ).all()
    fallback_by_reason = {str(reason): int(count) for reason, count in fallback_rows}

    # by_model 只统计真的调过模型的请求：缓存命中 / 限流 / missing_category
    # 虽然也可能带 model 名，但一次模型调用都没发生，算进去会把「模型用量」虚高。
    model_rows = db.execute(
        select(LlmMetric.model, func.count())
        .where(window, LlmMetric.model.is_not(None), LlmMetric.attempts > 0)
        .group_by(LlmMetric.model)
    ).all()
    by_model = {str(model): int(count) for model, count in model_rows}

    prompt_sum = db.execute(
        select(func.coalesce(func.sum(LlmMetric.tokens_prompt), 0)).where(window)
    ).scalar_one()
    completion_sum = db.execute(
        select(func.coalesce(func.sum(LlmMetric.tokens_completion), 0)).where(window)
    ).scalar_one()

    avg_latency = db.execute(
        select(func.avg(LlmMetric.latency_ms)).where(window)
    ).scalar_one()

    # 真实模型调用耗时：只算 attempts > 0 的行（缓存命中 / 限流 / 无 key 不算）
    model_calls = _scalar(
        db,
        select(func.count()).select_from(LlmMetric).where(window, LlmMetric.attempts > 0),
    )
    avg_model_latency = db.execute(
        select(func.avg(LlmMetric.latency_ms)).where(window, LlmMetric.attempts > 0)
    ).scalar_one()

    byok_calls = _scalar(
        db,
        select(func.count()).select_from(LlmMetric).where(window, LlmMetric.is_byok.is_(True)),
    )

    return MetricsOut(
        days=days,
        total_calls=total,
        llm_success=llm_success,
        cache_hits=cache_hits,
        fallbacks=fallbacks,
        fallback_by_reason=fallback_by_reason,
        by_model=by_model,
        tokens=TokensOut(prompt=int(prompt_sum or 0), completion=int(completion_sum or 0)),
        latency_ms=LatencyOut(
            avg=round(float(avg_latency), 1) if avg_latency is not None else None,
            p50=_percentile(db, cutoff, 0.50, total),
            p95=_percentile(db, cutoff, 0.95, total),
        ),
        model_latency_ms=LatencyOut(
            avg=round(float(avg_model_latency), 1) if avg_model_latency is not None else None,
            p50=_percentile(db, cutoff, 0.50, model_calls, only_model_calls=True),
            p95=_percentile(db, cutoff, 0.95, model_calls, only_model_calls=True),
        ),
        byok_calls=byok_calls,
        server_key_calls=total - byok_calls,
    )
