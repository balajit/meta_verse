"""OpenBao Secret Injection Source for Pydantic Settings."""

import os
from typing import Any, Dict, Optional, Tuple, Type
import hvac  # type: ignore[import-untyped]
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource
from meta_config.exceptions import SecretInjectionError
from meta_config.telemetry import log_config_error, log_config_event


class OpenBaoConfig:
    """Configuration container for OpenBao connection specs."""

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        mount_point: str = "secret",
    ) -> None:
        self.url = url or os.getenv("OPENBAO_ADDR", "http://127.0.0.1:8200")
        self.token = token or os.getenv("OPENBAO_TOKEN", "")
        self.mount_point = mount_point


class OpenBaoSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source that pulls configuration key-values from OpenBao KV engine."""

    def __init__(
        self,
        settings_cls: Type[BaseSettings],
        secret_path: Optional[str] = None,
        openbao_config: Optional[OpenBaoConfig] = None,
    ) -> None:
        super().__init__(settings_cls)
        self.secret_path = secret_path
        self.openbao_config = openbao_config or OpenBaoConfig()

    def get_field_value(self, field: Any, field_name: str) -> Tuple[Any, str, bool]:
        """Not used directly; __call__ extracts all values at once for efficiency."""
        return None, field_name, False

    def __call__(self) -> Dict[str, Any]:
        if not self.secret_path:
            return {}

        if not self.openbao_config.token:
            err = SecretInjectionError(
                message="OpenBao authentication token missing",
                secret_path=self.secret_path,
            )
            log_config_error("secret_injection", err, {"secret_path": self.secret_path})
            raise err

        try:
            client = hvac.Client(url=self.openbao_config.url, token=self.openbao_config.token)
            if not client.is_authenticated():
                raise SecretInjectionError(
                    message="OpenBao client authentication failed",
                    secret_path=self.secret_path,
                )

            response = client.secrets.kv.v2.read_secret_version(
                path=self.secret_path,
                mount_point=self.openbao_config.mount_point,
            )
            data: Dict[str, Any] = response.get("data", {}).get("data", {})
            log_config_event(
                event_type="secret_injection",
                status="success",
                metadata={"secret_path": self.secret_path, "keys_retrieved": list(data.keys())},
            )
            return data
        except Exception as exc:
            if isinstance(exc, SecretInjectionError):
                raise
            err = SecretInjectionError(
                message=f"Failed to fetch secrets from OpenBao: {str(exc)}",
                secret_path=self.secret_path,
            )
            log_config_error("secret_injection", err, {"secret_path": self.secret_path})
            raise err from exc