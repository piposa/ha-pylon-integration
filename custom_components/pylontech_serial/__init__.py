"""The Pylontech Serial integration."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN, CONF_SERIAL_PORT, CONF_BAUD_RATE, CONF_POLL_INTERVAL, CONF_BATTERY_CAPACITY, CONF_RS485
from .coordinator import PylontechCoordinator

PLATFORMS = ["sensor", "button", "switch", "number"]

_LOGGER = logging.getLogger(__name__)

def _platforms(coordinator):
    return ["sensor"] if coordinator.rs485 else PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Pylontech Serial from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    port = entry.options.get(CONF_SERIAL_PORT, entry.data.get(CONF_SERIAL_PORT))
    baud = entry.options.get(CONF_BAUD_RATE, entry.data.get(CONF_BAUD_RATE))
    interval = entry.options.get(CONF_POLL_INTERVAL, entry.data.get(CONF_POLL_INTERVAL))
    # Battery capacity might be in data (old) or options (new)
    capacity = entry.options.get(CONF_BATTERY_CAPACITY, entry.data.get(CONF_BATTERY_CAPACITY, 2.4))

    rs485 = entry.options.get(CONF_RS485, entry.data.get(CONF_RS485, False))
    coordinator = PylontechCoordinator(
        hass, port, baud, interval, capacity, rs485=rs485
    )

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _platforms(coordinator))

    if coordinator.rs485:
        return True

    async def async_send_command(call: ServiceCall) -> dict:
        """Handle the service call."""
        command = call.data.get("command")
        
        coordinator = next((item for item in hass.data[DOMAIN].values() if not item.rs485), None)
        if coordinator is None:
            raise ValueError("No Pylontech console integration found")

        response = await hass.async_add_executor_job(coordinator.send_raw_command, command)
        return {"response": response}

    hass.services.async_register(
        DOMAIN, 
        "send_command", 
        async_send_command,
        schema=vol.Schema({vol.Required("command"): cv.string}, extra=vol.ALLOW_EXTRA),
        supports_response=SupportsResponse.OPTIONAL
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _platforms(coordinator))
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(coordinator.shutdown)

    return unload_ok
