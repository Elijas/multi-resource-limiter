import asyncio

from token_throttle._interfaces._callbacks import RateLimiterCallbacks
from token_throttle._interfaces._interfaces import (
    BaseRateLimiter,
    PerModelConfig,
    PerModelConfigGetter,
    RateLimiterBackend,
    RateLimiterBackendBuilderInterface,
)
from token_throttle._interfaces._models import (
    CapacityReservation,
    FrozenUsage,
    Usage,
    frozen_usage,
)

_UNLIMITED_FLAG = "__rate_limiting_disabled__"


class RateLimiter(BaseRateLimiter):
    def __init__(
        self,
        cfg: PerModelConfig | PerModelConfigGetter,
        /,
        backend: RateLimiterBackendBuilderInterface,
        *,
        callbacks: RateLimiterCallbacks | None = None,
    ):
        self._backend = backend
        self._lock = asyncio.Lock()
        self._callbacks = callbacks

        def config_getter_decorator(model_name: str) -> PerModelConfig:
            """Sets the model_family field if it is not set."""
            if not model_name:
                raise ValueError("model_name cannot be empty")
            r = cfg(model_name) if callable(cfg) else cfg
            return (
                r
                if r.model_family
                else r.model_copy(update={"model_family": model_name})
            )

        self._config_getter = config_getter_decorator
        self._model_family_to_backend: dict[str, RateLimiterBackend] = {}

    async def acquire_capacity(self, usage: Usage, model: str) -> CapacityReservation:
        usage = frozen_usage(usage)
        limit_config = self._config_getter(model)
        if limit_config.is_unlimited:
            if usage:
                raise ValueError("Usage must be empty for unlimited capacity")
            return CapacityReservation(
                usage={},
                model_family=_UNLIMITED_FLAG,
            )
        return await self._acquire_capacity(usage, limit_config)

    async def acquire_capacity_for_request(
        self,
        *,
        extra_usage: dict | None,
        **kwargs,
    ) -> CapacityReservation:
        model = kwargs.get("model")
        if not model:
            raise ValueError("'model' parameter is required")

        limit_config = self._config_getter(model)
        if limit_config.is_unlimited:
            return CapacityReservation(
                usage={},
                model_family=_UNLIMITED_FLAG,
            )
        if limit_config.usage_counter is None:
            raise ValueError("limit_config.usage_counter cannot be None")

        usage = dict(limit_config.usage_counter(**kwargs))
        if extra_usage:
            for k, v in extra_usage.items():
                if k not in usage:
                    raise ValueError(
                        f"Usage key '{k}' not found in usage counter",
                    )
                usage[k] += v
        return await self._acquire_capacity(frozen_usage(usage), limit_config)

    async def _acquire_capacity(
        self,
        usage: FrozenUsage,
        limit_config: PerModelConfig,
    ) -> CapacityReservation:
        if set(usage) != set(limit_config.quotas.names):
            raise ValueError(
                f"Usage keys {set(usage)} do not match quota keys {set(limit_config.quotas.names)}",
            )
        for metric, amount_ in usage.items():
            amount = float(amount_)
            if amount < 0:
                raise ValueError(f"Usage value for {metric} must be non-negative")
            for quota in limit_config.quotas.get_quotas(metric):
                if amount > float(quota.limit):
                    raise ValueError(
                        f"Usage value for {metric} ({amount}) exceeds the limit ({quota.limit})",
                    )

        backend = await self._get_backend(limit_config)
        await backend.await_for_capacity(usage)
        reservation = CapacityReservation(
            usage=usage,
            model_family=limit_config.get_model_family(),
        )

        return reservation

    async def refund_capacity(
        self,
        actual_usage: Usage,
        reservation: CapacityReservation,
    ) -> None:
        if reservation.model_family == _UNLIMITED_FLAG:
            if actual_usage:
                raise ValueError(
                    "Usage must be empty for unlimited capacity reservations",
                )
            return
        if set(actual_usage) != set(reservation.usage):
            raise ValueError(
                f"Usage keys {set(actual_usage)} do not match reservation usage keys {set(reservation.usage)}",
            )
        await self._refund_capacity(
            actual_usage,
            reservation,
        )

    async def refund_capacity_from_response(
        self,
        reservation: CapacityReservation,
        **kwargs,
    ) -> None:
        if reservation.model_family == _UNLIMITED_FLAG:
            return
        actual_usage = {"tokens": kwargs["usage"]["total_tokens"], "requests": 1}
        if set(actual_usage) != set(reservation.usage):
            raise ValueError(
                f"Usage keys {set(actual_usage)} do not match reservation usage keys {set(reservation.usage)}",
            )
        await self._refund_capacity(
            actual_usage,
            reservation,
        )

    async def _refund_capacity(
        self,
        actual_usage: Usage,
        reservation: CapacityReservation,
    ) -> None:
        actual_usage = frozen_usage(actual_usage)
        # No need to call _config_getter since we already have the model_family
        # Just get the backend directly
        backend = self._model_family_to_backend.get(reservation.model_family)
        if backend is None:
            raise ValueError(
                f"Backend not found for model family {reservation.model_family}",
            )
        await backend.refund_capacity(reservation.get_usage(), actual_usage)

    async def _get_backend(self, cfg: PerModelConfig) -> RateLimiterBackend:
        if not cfg.model_family:
            raise ValueError("cfg.model_family cannot be empty")
        if cfg.model_family in self._model_family_to_backend:
            return self._model_family_to_backend[cfg.model_family]

        async with self._lock:
            # Check again after acquiring lock
            if cfg.model_family in self._model_family_to_backend:
                return self._model_family_to_backend[cfg.model_family]

            backend = self._backend.build(cfg, callbacks=self._callbacks)

            self._model_family_to_backend[cfg.model_family] = backend
            return backend
