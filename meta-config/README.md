# meta-config

Enterprise settings management framework with strongly typed validation, strict boot sequence validation, dynamic OpenBao secret injection, and native structured telemetry integration.

## Architectural Objectives

1. **Fail-Fast Boot Validation**: Halt process startup immediately when configuration is missing, malformed, or unauthorized. Prevent partially configured applications from entering execution states.
2. **Runtime Immutability**: All configuration settings models are strictly frozen upon instantiation (`frozen=True`) to prevent runtime configuration drift or race conditions.
3. **Secret Injection Isolation**: Automatically pull runtime secrets from OpenBao KV engines prior to application boot while keeping sensitive data out of environment variables and disk persistence.
4. **Agentic Observability**: Emit structured, contextual JSON logs and OpenTelemetry spans during the configuration lifecycle without exposing secret values.

## Installation & Environment

Managed via `uv` within the monorepo workspace:

```bash
uv pip install -e ./meta-config

## Usage example

    from typing import SecretStr
    from pydantic import Field
    from meta_config.base import MetaBaseSettings
    from meta_config.loaders.openbao import OpenBaoConfig
    
    class DatabaseSettings(MetaBaseSettings):
        host: str = Field(description="Database hostname")
        port: int = Field(default=5432, ge=1, le=65535)
        username: str = Field(description="Database user")
        password: SecretStr = Field(description="Database password from OpenBao")
    
        model_config = {
            "openbao_path": "secret/data/backend/database",
        }
    
    # Boot loading and validation
    try:
        settings = DatabaseSettings()
    except Exception as err:
        # Boot halts automatically via MetaBaseSettings fail-fast handler
        raise
