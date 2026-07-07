"""Button platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AnkerSolixOfficialCoordinator
from .base_entity import AnkerSolixBaseEntity, async_setup_entities_with_retry

_LOGGER = logging.getLogger(__name__)

def _is_button_entity(key: str, config: dict) -> bool:
    """Check if config represents a button entity."""
    return config.get("display_type") == "button"

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button platform."""
    coordinator: AnkerSolixOfficialCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    await async_setup_entities_with_retry(
        hass=hass,
        coordinator=coordinator,
        async_add_entities=async_add_entities,
        entity_filter=_is_button_entity,
        entity_factory=lambda c, k, cfg: ModbusLocalDeviceButton(c, k, cfg),
        platform_name="button",
    )

class ModbusLocalDeviceButton(AnkerSolixBaseEntity, ButtonEntity):
    """Modbus local device button entity."""

    def __init__(
        self,
        coordinator: AnkerSolixOfficialCoordinator,
        key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize button."""
        super().__init__(coordinator, key, config)
        # Extraemos el valor a escribir del YAML (por defecto 1)
        self._write_value = config.get("write_value", 1)

    async def async_press(self) -> None:
        """Handle the button press."""
        # Comprobar condiciones si existen (ej. no iniciar si no hay coche)
        condition_passed, hint_key = self._check_write_condition()
        if not condition_passed:
            await self._raise_write_condition_error(hint_key)

        address = self._config.get("address")
        if address is None:
            _LOGGER.error("Button %s has no address configured", self._entity_key)
            return

        try:
            address = int(address)
            value = int(self._write_value)
        except (ValueError, TypeError) as e:
            _LOGGER.error("Invalid address or value for button %s: %s", self._entity_key, e)
            return

        data_type = self._config.get("data_type", "UINT16")
        
        _LOGGER.info(
            "Pressing button %s | address=%d (0x%04X), write_value=%d",
            self._entity_key, address, address, value
        )

        try:
            result = await self.coordinator.modbus_manager.write_register(
                address, value, data_type
            )
            if result.success:
                _LOGGER.info("Button press SUCCESS | %s", self._entity_key)
                
                # Escribir en el logbook de Home Assistant
                device_name = self.coordinator.device_name or "Anker Solix"
                entity_name = self.name or self._entity_key
                await self.coordinator.hass.services.async_call(
                    "logbook",
                    "log",
                    {
                        "name": device_name,
                        "message": f"Pressed {entity_name}",
                        "entity_id": self.entity_id,
                        "domain": DOMAIN,
                    },
                    blocking=False,
                )
            else:
                _LOGGER.error("Button press FAILED | %s, reason: %s", self._entity_key, result.error_reason)
        except Exception as e:
            _LOGGER.error("Button press EXCEPTION | %s: %s", self._entity_key, e)