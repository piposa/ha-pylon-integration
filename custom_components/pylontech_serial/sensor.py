"""Sensor platform for Pylontech Serial."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfEnergy,
    PERCENTAGE,
    EntityCategory,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .entity import PylontechSystemEntity, PylontechBatteryEntity

from .const import DOMAIN
# from .structs import PylontechSystem, PylontechBattery # Not strictly needed at runtime if we don't type hint heavily, but good for ref.

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.rs485:
        _setup_rs485_sensors(entry, coordinator, async_add_entities)
        return
    unique_id_prefix = entry.entry_id
    entities = []
    
    # --- System Sensors ---
    # Voltage
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_volt", 
        UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, "voltage",
        state_class=SensorStateClass.MEASUREMENT
    ))
    # Current
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_curr", 
        UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, "current",
        state_class=SensorStateClass.MEASUREMENT
    ))
    # SOC
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_soc", 
        PERCENTAGE, SensorDeviceClass.BATTERY, "soc",
        state_class=SensorStateClass.MEASUREMENT
    ))
    # Power
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_power", 
        UnitOfPower.WATT, SensorDeviceClass.POWER, "power",
        state_class=SensorStateClass.MEASUREMENT
    ))
    # Energy In
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_energy_in", 
        UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, "energy_in",
        state_class=SensorStateClass.TOTAL_INCREASING
    ))
    # Energy Out
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_energy_out", 
        UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, "energy_out",
        state_class=SensorStateClass.TOTAL_INCREASING
    ))
    # Stored Energy
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_energy_stored", 
        UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY_STORAGE, "energy_stored",
        state_class=SensorStateClass.MEASUREMENT
    ))
    # SOH (System)
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_soh", 
        PERCENTAGE, SensorDeviceClass.BATTERY, "soh",
        state_class=SensorStateClass.MEASUREMENT
    ))
    # Cycles (System)
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_cycles", 
        None, None, "cycles",
        state_class=SensorStateClass.MEASUREMENT
    ))
    # Raw Data (System)
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_raw", 
        None, None, "raw",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False
    ))

    # Info Sensors (Diagnostic)
    entities.append(PylontechSystemSensor(coordinator, unique_id_prefix, "sys_cell_count", None, None, "cell_count", entity_category=EntityCategory.DIAGNOSTIC))
    entities.append(PylontechSystemSensor(coordinator, unique_id_prefix, "sys_fw_version", None, None, "fw_version", entity_category=EntityCategory.DIAGNOSTIC))
    entities.append(PylontechSystemSensor(coordinator, unique_id_prefix, "sys_spec", None, None, "spec", entity_category=EntityCategory.DIAGNOSTIC))
    entities.append(PylontechSystemSensor(coordinator, unique_id_prefix, "sys_barcode", None, None, "barcode", entity_category=EntityCategory.DIAGNOSTIC))
    entities.append(PylontechSystemSensor(coordinator, unique_id_prefix, "sys_bms_time", None, None, "bms_time", entity_category=EntityCategory.DIAGNOSTIC))


    # --- Per Battery Sensors ---
    # We iterate initially available batteries. If batteries increase dynamically, we need execution loop logic or reload.
    # Standard practice: Iterate current data.
    if coordinator.data and coordinator.data.batteries:
        for bat in coordinator.data.batteries:
            bat_id = bat.sys_id
            
            # Standard Sensors
            entities.append(PylontechBatterySensor(coordinator, unique_id_prefix, bat_id, "volt", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, "voltage"))
            entities.append(PylontechBatterySensor(coordinator, unique_id_prefix, bat_id, "curr", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, "current"))
            entities.append(PylontechBatterySensor(coordinator, unique_id_prefix, bat_id, "temp", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, "temperature"))
            entities.append(PylontechBatterySensor(coordinator, unique_id_prefix, bat_id, "soc", PERCENTAGE, SensorDeviceClass.BATTERY, "soc"))
            entities.append(PylontechBatterySensor(coordinator, unique_id_prefix, bat_id, "power", UnitOfPower.WATT, SensorDeviceClass.POWER, "power"))
            entities.append(PylontechBatterySensor(coordinator, unique_id_prefix, bat_id, "energy_stored", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY_STORAGE, "energy_stored"))
            entities.append(PylontechBatterySensor(coordinator, unique_id_prefix, bat_id, "status", None, None, "status"))
            
            # Diagnostic
            entities.append(PylontechBatterySensor(coordinator, unique_id_prefix, bat_id, "raw", None, None, "raw", entity_category=EntityCategory.DIAGNOSTIC, entity_registry_enabled_default=False))

    async_add_entities(entities)


class PylontechSystemSensor(PylontechSystemEntity, SensorEntity):
    """Representation of a System-wide Sensor."""

    def __init__(self, coordinator, unique_id_prefix, key, unit, device_class, attr_name, state_class=None, entity_category=None, entity_registry_enabled_default=True):
        super().__init__(coordinator)
        self._attribute_key = attr_name # field name in struct
        self._unit = unit
        self._device_class = device_class
        self._attr_state_class = state_class
        self._attr_entity_category = entity_category
        self._attr_entity_registry_enabled_default = entity_registry_enabled_default
        
        self._attr_unique_id = f"{unique_id_prefix}_{key}"
        self._attr_translation_key = key

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        return getattr(self.coordinator.data, self._attribute_key, None)

    @property
    def native_unit_of_measurement(self):
        return self._unit

    @property
    def device_class(self):
        return self._device_class
    
    @property
    def extra_state_attributes(self):
        # Update device info dynamically if available in data
        if self.coordinator.data and self.coordinator.data.model:
             # This is a bit hacky, HA reads device_info mostly at setup.
             # But we can try to return updated info via the registry if we wanted.
             pass
        return {}


class PylontechBatterySensor(PylontechBatteryEntity, SensorEntity):
    """Representation of a Per-Battery Sensor."""

    def __init__(self, coordinator, unique_id_prefix, bat_id, suffix, unit, device_class, attr_name, entity_category=None, entity_registry_enabled_default=True):
        super().__init__(coordinator, bat_id)
        self._attribute_key = attr_name
        self._unit = unit
        self._device_class = device_class
        self._attr_entity_category = entity_category
        self._attr_entity_registry_enabled_default = entity_registry_enabled_default
        
        self._attr_unique_id = f"{unique_id_prefix}_bat{bat_id}_{suffix}"
        self._attr_translation_key = f"bat_{suffix}"

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        for b in self.coordinator.data.batteries:
            if b.sys_id == self._bat_id:
                return getattr(b, self._attribute_key, None)
        return None

    @property
    def native_unit_of_measurement(self):
        return self._unit

    @property
    def device_class(self):
        return self._device_class


def _setup_rs485_sensors(entry, coordinator, async_add_entities):
    """Register newly discovered readings without changing existing entity IDs."""
    registered = set()

    @callback
    def add_readings():
        entities = []
        for module, readings in coordinator.data.items():
            for key in readings:
                identity = (module, key)
                if identity not in registered:
                    registered.add(identity)
                    entities.append(PylontechRS485Sensor(coordinator, entry.entry_id, module, key))
        if entities:
            async_add_entities(entities)

    add_readings()
    entry.async_on_unload(coordinator.async_add_listener(add_readings))


_MEASUREMENTS = {
    "packVolt": (UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
    "packCurrent": (UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
    "packPower": (UnitOfPower.WATT, SensorDeviceClass.POWER),
    "packSOC": (PERCENTAGE, SensorDeviceClass.BATTERY),
    "packCapacity": ("Ah", None),
    "packCapacityRemain": ("Ah", None),
    "packImbalance": (PERCENTAGE, None),
    "bmsTemperature": (UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
}


class PylontechRS485Sensor(PylontechBatteryEntity, SensorEntity):
    """An RS485 reading attached to its numbered module."""

    def __init__(self, coordinator, entry_id, module, key):
        super().__init__(coordinator, module)
        self._key = key
        self._attr_unique_id = f"{entry_id}_rs485_bat{module}_{key.lower()}"
        self._attr_name = key
        measurement = _MEASUREMENTS.get(key)
        if key.startswith("cellVoltage"):
            measurement = (UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE)
        if key.startswith("cellTemperature"):
            measurement = (UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE)
        if measurement:
            self._attr_native_unit_of_measurement, self._attr_device_class = measurement
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key != "packState":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            if "VoltLimit" in key or "VoltageLimit" in key:
                self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
                self._attr_device_class = SensorDeviceClass.VOLTAGE
            elif "CurrentLimit" in key:
                self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
                self._attr_device_class = SensorDeviceClass.CURRENT
            elif "TempLimit" in key:
                self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
                self._attr_device_class = SensorDeviceClass.TEMPERATURE
            elif key == "cmdChainDuration":
                self._attr_native_unit_of_measurement = "s"
                self._attr_device_class = SensorDeviceClass.DURATION
            elif key == "nextCycletime":
                self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def available(self):
        return super().available and self._key in self.coordinator.data.get(self._bat_id, {})

    @property
    def native_value(self):
        return self.coordinator.data.get(self._bat_id, {}).get(self._key)
