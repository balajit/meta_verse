from typing import Type, TypeVar, Dict, Optional
from pydantic_settings import BaseSettings

T = TypeVar("T", bound=BaseSettings)


class ConfigRegistry:
    """Type-safe central store mapping BaseSettings classes to instantiated objects."""

    _registry: Dict[Type[BaseSettings], BaseSettings] = {}

    @classmethod
    def register(cls, config: BaseSettings) -> None:
        """Stores a hydrated settings instance by its class type."""
        cls._registry[type(config)] = config

    @classmethod
    def resolve(cls, config_cls: Type[T]) -> Optional[T]:
        """Retrieves a hydrated settings instance matching the requested class type."""
        return cls._registry.get(config_cls)  # type: ignore[return-value]

    @classmethod
    def clear(cls) -> None:
        """Clears registry state (useful between unit tests)."""
        cls._registry.clear()