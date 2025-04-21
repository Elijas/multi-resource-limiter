import re

import redis.asyncio as redis

from multi_resource_limiter.factories.openai.token_counter import OpenAIUsageCounter
from multi_resource_limiter.interfaces.callbacks import (
    RateLimiterCallbacks,
    create_loguru_callbacks,
)
from multi_resource_limiter.interfaces.interfaces import PerModelConfig
from multi_resource_limiter.interfaces.models import Quota, SecondsIn, UsageQuotas
from multi_resource_limiter.limiter_backends.redis.backend import RedisBackendBuilder
from multi_resource_limiter.rate_limiter import RateLimiter


def openai_model_family_getter(model: str, /) -> str:
    # E.g. gpt-4-0314 and gpt-4-0613 count against the same gpt-4 quota
    return re.sub(r"-\d+$", "", model)


def create_openai_redis_rate_limiter(
    redis_client: redis.Redis,
    *,
    rpm: int,
    tpm: int,
    callbacks: RateLimiterCallbacks | None = None,
) -> RateLimiter:
    return RateLimiter(
        lambda model_name: PerModelConfig(
            quotas=UsageQuotas(
                [
                    Quota(metric="requests", limit=rpm, per_seconds=SecondsIn.MINUTE),
                    Quota(metric="tokens", limit=tpm, per_seconds=SecondsIn.MINUTE),
                ],
            ),
            usage_counter=OpenAIUsageCounter(),
            model_family=openai_model_family_getter(model_name),
        ),
        backend=RedisBackendBuilder(redis_client),
        callbacks=callbacks
        or create_loguru_callbacks(
            missing_consumption_data="INFO",
        ),
    )
