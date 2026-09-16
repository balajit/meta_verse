import importlib.metadata
import logging
import sys
from typing import Dict

from pydantic_settings import BaseSettings

from meta_application_builder.config.config_bao import (
    AppConfig,
    BootstrapSettings,
    DynamicHostContainer,
    OpenBaoClient,
)

logger = logging.getLogger("meta_application_builder.bootstrap")


async def bootstrap_application_configuration(
    bao_client: OpenBaoClient,
    bootstrap_settings: BootstrapSettings,
) -> DynamicHostContainer:
    """Hydrates secrets from OpenBao, discovers library schemas via entry points, and executes fail-fast validation."""
    secret_path = f"{bootstrap_settings.app_env}/app"
    logger.info("Fetching dynamic startup secrets from OpenBao path: 'meta-builder/%s'", secret_path)

    try:
        raw_secrets = await bao_client.get_kv2_secrets(
            mount_path="meta-builder",
            secret_path=secret_path,
        )
        normalized_secrets = {k.lower(): v for k, v in raw_secrets.items()}
    except Exception as err:
        logger.critical("Boot failure: Could not reach or fetch secrets from OpenBao: %s", err)
        sys.exit(1)

    # 1. Instantiate Core Host Application Settings
    try:
        host_config = AppConfig(**normalized_secrets)
    except Exception as err:
        logger.critical("Boot failure: Host AppConfig validation failed: %s", err)
        sys.exit(1)

    # 2. Discover and Hydrate Entry-Point Library Schemas
    # Discovers all packages registering under [project.entry-points."meta_builder.config_schemas"]
    discovered_child_configs: Dict[str, BaseSettings] = {}
    entry_points = importlib.metadata.entry_points(group="meta_builder.config_schemas")

    for ep in entry_points:
        logger.info("Discovering library config entry-point: '%s' (%s)", ep.name, ep.value)
        try:
            schema_cls = ep.load()
            if not issubclass(schema_cls, BaseSettings):
                raise TypeError(f"Entry-point target '{ep.value}' must inherit from BaseSettings")

            # Hydrate schema using OpenBao secrets + OS env + local .env fallbacks
            hydrated_instance = schema_cls(**normalized_secrets)
            discovered_child_configs[ep.name] = hydrated_instance
            logger.info("Successfully hydrated configuration for plugin: '%s'", ep.name)

        except Exception as err:
            logger.critical(
                "Fail-fast: Validation or hydration failure for library plugin '%s' [%s]: %s",
                ep.name,
                ep.value,
                err,
            )
            sys.exit(1)

    return DynamicHostContainer(host_config=host_config, child_configs=discovered_child_configs)