"""Sensor platform for Aquael BT."""

from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEVICE_TYPE_FLOW_HEATER, DOMAIN, MANUFACTURER
from .parser import AquaelAdvertisement

TEMPERATURE_KEY = PassiveBluetoothEntityKey("temperature", None)
RSSI_KEY = PassiveBluetoothEntityKey("signal_strength", None)

TEMPERATURE_DESCRIPTION = SensorEntityDescription(
    key="temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
)
RSSI_DESCRIPTION = SensorEntityDescription(
    key="signal_strength",
    device_class=SensorDeviceClass.SIGNAL_STRENGTH,
    native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    state_class=SensorStateClass.MEASUREMENT,
)


def _sensor_update_to_bluetooth_data_update(
    update: AquaelAdvertisement | None,
) -> PassiveBluetoothDataUpdate:
    """Convert decoded Aquael data into Home Assistant entities."""
    if update is None:
        return PassiveBluetoothDataUpdate()

    device_info = DeviceInfo(
        connections={("bluetooth", update.address)},
        identifiers={(DOMAIN, update.address)},
        manufacturer=MANUFACTURER,
        model=update.model,
        name=update.model,
    )
    descriptions = {}
    names = {}
    data = {}

    if update.rssi is not None:
        descriptions[RSSI_KEY] = RSSI_DESCRIPTION
        names[RSSI_KEY] = "Signalstärke"
        data[RSSI_KEY] = update.rssi

    if update.device_type == DEVICE_TYPE_FLOW_HEATER and update.temperature is not None:
        descriptions[TEMPERATURE_KEY] = TEMPERATURE_DESCRIPTION
        names[TEMPERATURE_KEY] = "Wassertemperatur"
        data[TEMPERATURE_KEY] = update.temperature

    return PassiveBluetoothDataUpdate(
        devices={None: device_info},
        entity_descriptions=descriptions,
        entity_names=names,
        entity_data=data,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    processor = PassiveBluetoothDataProcessor(
        _sensor_update_to_bluetooth_data_update
    )
    entry.async_on_unload(
        processor.async_add_entities_listener(
            AquaelBluetoothSensorEntity, async_add_entities
        )
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class AquaelBluetoothSensorEntity(PassiveBluetoothProcessorEntity, SensorEntity):
    @property
    def native_value(self) -> float | int | str | None:
        return self.processor.entity_data.get(self.entity_key)
