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
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, MANUFACTURER, MODEL_FLOW_HEATER
from .parser import AquaelAdvertisement

TEMPERATURE_KEY = PassiveBluetoothEntityKey("temperature", None)
TEMPERATURE_DESCRIPTION = SensorEntityDescription(
    key="temperature",
    translation_key="water_temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
)


def _sensor_update_to_bluetooth_data_update(
    update: AquaelAdvertisement | None,
) -> PassiveBluetoothDataUpdate:
    """Convert decoded Aquael data into Home Assistant entities."""
    if update is None or update.temperature is None:
        return PassiveBluetoothDataUpdate()

    return PassiveBluetoothDataUpdate(
        devices={
            None: DeviceInfo(
                identifiers={(DOMAIN, MODEL_FLOW_HEATER)},
                manufacturer=MANUFACTURER,
                model=MODEL_FLOW_HEATER,
                name=MODEL_FLOW_HEATER,
            )
        },
        entity_descriptions={TEMPERATURE_KEY: TEMPERATURE_DESCRIPTION},
        entity_names={TEMPERATURE_KEY: "Water temperature"},
        entity_data={TEMPERATURE_KEY: update.temperature},
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Aquael BT sensors."""
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


class AquaelBluetoothSensorEntity(
    PassiveBluetoothProcessorEntity, SensorEntity
):
    """A sensor provided by Aquael BT advertisements."""

    @property
    def native_value(self) -> float | int | str | None:
        """Return the sensor value."""
        return self.processor.entity_data.get(self.entity_key)
