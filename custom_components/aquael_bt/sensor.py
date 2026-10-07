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
from homeassistant.const import EntityCategory, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_TYPE_FLOW_HEATER,
    DEVICE_TYPE_ULTRAMAX,
    DOMAIN,
    MANUFACTURER,
    MODEL_ULTRAMAX,
)
from .gatt import AquaelGattCoordinator, async_get_gatt_coordinator
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

    address = entry.unique_id
    if address is None:
        return

    gatt_coordinator = await async_get_gatt_coordinator(hass, entry)
    if (
        gatt_coordinator is None
        or gatt_coordinator.device_type != DEVICE_TYPE_ULTRAMAX
    ):
        return

    async_add_entities([AquaelUltramaxWaveModeRawSensor(gatt_coordinator, address)])


class AquaelBluetoothSensorEntity(PassiveBluetoothProcessorEntity, SensorEntity):
    @property
    def native_value(self) -> float | int | str | None:
        return self.processor.entity_data.get(self.entity_key)


class AquaelUltramaxWaveModeRawSensor(
    CoordinatorEntity[AquaelGattCoordinator], SensorEntity
):
    """Raw ULTRAMAX wave mode value for protocol reverse engineering."""

    _attr_has_entity_name = True
    _attr_translation_key = "wave_mode_raw"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:sine-wave"

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator)
        self._address = address
        self._attr_unique_id = f"{address}_wave_mode_raw"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            connections={("bluetooth", self._address)},
            identifiers={(DOMAIN, self._address)},
            manufacturer=MANUFACTURER,
            model=MODEL_ULTRAMAX,
            name=MODEL_ULTRAMAX,
        )

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return int(self.coordinator.data["wave_mode_raw"])

    @property
    def extra_state_attributes(self) -> dict[str, int | float]:
        if not self.coordinator.data:
            return {}
        data = self.coordinator.data
        return {
            "day_flow_raw": int(data["day_flow_raw"]),
            "day_flow_percent": round(float(data["day_flow_percent"]), 2),
            "day_min_flow_raw": int(data["day_min_flow_raw"]),
            "day_min_flow_percent": round(float(data["day_min_flow_percent"]), 2),
            "night_flow_raw": int(data["night_flow_raw"]),
            "night_flow_percent": round(float(data["night_flow_percent"]), 2),
            "night_min_flow_raw": int(data["night_min_flow_raw"]),
            "night_min_flow_percent": round(float(data["night_min_flow_percent"]), 2),
            "wave_period_seconds": int(data["wave_period_seconds"]),
        }
