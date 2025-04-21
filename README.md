# multi-resource-limiter

[No good solution existed](https://gist.github.com/justinvanwinkle/d9f04950083c4554835c1a35f9d22dad) for rate limiting multiple quotas (e.g. satisfy all: request/minute AND token/minute AND cost_usd/minute AND requesttoken/minute AND completiontoken/minute, etc.), so I built as a fork of [openlimit](https://github.com/shobrook/openlimit/issues/20#issuecomment-2782677483). Treat this as an early preview more rather than a stable production release, but it satisfied for my needs as it is.

### Features

Here are the key features of `multi-resource-limiter`, explained:

- **Multi-Resource Limiting:**

  - Simultaneously enforce limits on multiple distinct resource types for a single operation (e.g., limit both the number of API requests _and_ the number of tokens consumed within those requests).
  - Define simultaneous different quotas for different resources (e.g., 60 requests/minute AND 1,000 requests/day AND 1,000,000 tokens/minute).

- **Accurate Capacity Management & Refunding:**

  - Implements a reserve-then-adjust mechanism (`acquire_capacity` followed by `refund_capacity`).
  - Initially reserves the maximum potential usage for an operation.
  - Allows refunding unused capacity _or_ accounting for overuse if the actual usage differs from the reservation, ensuring limits are accurately enforced based on _actual_ consumption.

- **Asyncio Native:**

  - Built from the ground up using `asyncio` for non-blocking operation, ideal for high-throughput applications interacting with external APIs.

- **Flexible Time Windows:**

  - Define quotas over various time periods (e.g., per second, per minute, per hour, per day, or anything in-between) using the `per_seconds` parameter in `Quota`.
  - Enforce limits across multiple windows concurrently for the same resource (e.g., limit requests per minute _and_ requests per day).

- **Correctness & Atomicity:**

  - Designed to avoid common race conditions found in simpler rate limiters, especially when used with distributed backends like Redis.
  - The provided Redis backend uses locks and appropriate commands to guarantee atomic updates to capacity across multiple workers/processes.

- **Pluggable Backend Architecture:**

  - Core logic is separated from the storage mechanism via `RateLimiterBackend` and `RateLimiterBackendBuilder` interfaces.
  - Ships with a robust `RedisBackend` for distributed rate limiting.
  - Allows implementing custom backends (e.g., in-memory for single process, other databases) if needed.

- **Configurable Per "Model" or Endpoint:**

  - Apply different sets of `UsageQuotas` to different logical entities (referred to as `model` or `model_family` internally, e.g., specific API endpoints, different LLM versions sharing a quota).
    - i.e. This allows for gpt-4o and gpt-4o-mini automatically have separate quotas, while gpt-4o-20241203 and gpt-4o-20241024 are just aliases of each other but are counted in the same quota bucket instance (i.e. belong to the same model_family).
  - Supports dynamic configuration lookups via a `PerModelConfigGetter` callable.

- **Extensible Usage Counting:**

  - Define custom logic (`UsageCounter`) to calculate the resource usage of a given request _before_ it happens (e.g., estimate token count for an LLM request based on input messages).

- **Observability Hooks:**
  - Provides callbacks (`RateLimiterCallbacks`) for monitoring key events like starting to wait for capacity, consuming capacity, refunding capacity, and detecting missing state in the backend. Includes `loguru` integration helpers.

### Getting started

For out of the box experience just do `limiter = create_openai_redis_rate_limiter()`, and use it as in the [example-1](https://github.com/shobrook/openlimit/issues/20#issuecomment-2782677483) or [example-2](https://gist.github.com/justinvanwinkle/d9f04950083c4554835c1a35f9d22dad)

Note, that it's fully customizable

- You can limit bananas per 32 seconds and apples per 2 minutes
- You can use your own backend (e.g. in-memory, redis, etc.) instead of Redis, etc.
- etc.
