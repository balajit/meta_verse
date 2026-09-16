import logging
from typing import Any, Dict

import httpx
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

class BuildServiceConfig(BaseSettings):
    """Configuration schema for BuildApplicationService compilation pipeline."""

    opa_policy_uri: str = Field(default="policies/governance.rego")
    cas_path: str = Field(default="/var/data/cas")
    max_ast_nodes: int = Field(default=5000)

    model_config = SettingsConfigDict(
        env_prefix="BUILD_SERVICE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

class BootstrapSettings(BaseSettings):
    """Bootstrap configuration required to connect to OpenBao on startup."""

    app_env: str = Field(default="dev", validation_alias="APP_ENV")
    bao_addr: str = Field(default="http://localhost:8200", validation_alias="BAO_ADDR")
    bao_token: SecretStr = Field(default=SecretStr("root"), validation_alias="BAO_TOKEN")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )


class AppConfig(BaseSettings):
    """Core host application settings schema (infrastructure & global flags)."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_env: str = Field(default="dev")
    database_username: str = Field(...)
    database_password: SecretStr = Field(...)
    jwt_secret: SecretStr = Field(...)
    third_party_api_key: SecretStr = Field(default=SecretStr(""))


class DynamicHostContainer:
    """Runtime configuration aggregator holding host settings and dynamically attached child settings."""

    def __init__(self, host_config: AppConfig, child_configs: Dict[str, BaseSettings]) -> None:
        self.host = host_config
        self._child_configs = child_configs

        # Dynamically attach child configs as attributes (e.g., container.build_service or container.brain)
        # Enables Protocol factories (.from_provider(container)) to extract settings cleanly.
        for ep_name, config_instance in child_configs.items():
            setattr(self, ep_name, config_instance)

    def get_child(self, name: str) -> BaseSettings:
        """Retrieves a registered child configuration object by its entry-point name."""
        if name not in self._child_configs:
            raise KeyError(f"No library configuration registered under entry-point group key '{name}'")
        return self._child_configs[name]


class OpenBaoClient:
    """Async client for OpenBao KV-v2 secrets engine."""

    def __init__(self, bao_addr: str, bao_token: str) -> None:
        self.bao_addr = bao_addr.rstrip("/")
        self.headers = {"X-Vault-Token": bao_token}

    async def get_kv2_secrets(self, mount_path: str, secret_path: str) -> dict[str, Any]:
        url = f"{self.bao_addr}/v1/{mount_path}/data/{secret_path}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                payload = response.json()
                return payload.get("data", {}).get("data", {})
            except httpx.HTTPStatusError as e:
                logger.error(f"Failed to fetch secrets from OpenBao [{url}]: {e.response.status_code}")
                raise RuntimeError(f"OpenBao secret retrieval failed: {e}") from e
            except httpx.RequestError as e:
                logger.error(f"Could not connect to OpenBao server at {self.bao_addr}: {e}")
                raise RuntimeError(f"OpenBao connection error: {e}") from e