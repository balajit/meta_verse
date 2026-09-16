"""Immutable configuration models for resilience policies."""

from meta_config import MetaBaseSettings
from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict


class ResilienceConfig(MetaBaseSettings):
    """Global configuration for meta-resiliency runtime behavior."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="forbid",
        env_prefix="META_RESILIENCY_",
    )

    enable_telemetry: bool = Field(default=True, description="Enable OpenTelemetry tracing")
    service_name: str = Field(default="meta-resiliency", description="Service identifier for logs and traces")
    default_timeout_seconds: float = Field(default=30.0, ge=0.1, description="Default operational timeout")
    max_retry_attempts: int = Field(default=3, ge=1, description="Default maximum retry attempts")
    retry_backoff_min_seconds: float = Field(default=0.1, ge=0.01, description="Minimum exponential backoff delay")
    retry_backoff_max_seconds: float = Field(default=5.0, ge=0.1, description="Maximum exponential backoff delay")
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1, description="Failures required to open circuit")
    circuit_breaker_recovery_timeout: float = Field(default=30.0, ge=0.1, description="Seconds before testing half-open")
    rate_limiter_max_calls: int = Field(default=100, ge=1, description="Calls allowed in rate limiter period")
    rate_limiter_period_seconds: float = Field(default=1.0, ge=0.01, description="Rate limit evaluation period")
    rate_limiter_storage_uri: str = Field(default="memory://", description="Backend storage URI for rate limits")
    bulkhead_max_concurrent: int = Field(default=50, ge=1, description="Maximum concurrent executions permitted in bulkhead")

    @model_validator(mode="after")
    def validate_backoff_bounds(self) -> "ResilienceConfig":
        """Ensures minimum retry backoff does not exceed maximum retry backoff."""
        if self.retry_backoff_min_seconds > self.retry_backoff_max_seconds:
            raise ValueError(
                f"retry_backoff_min_seconds ({self.retry_backoff_min_seconds}) "
                f"cannot be greater than retry_backoff_max_seconds ({self.retry_backoff_max_seconds})"
            )
        return self