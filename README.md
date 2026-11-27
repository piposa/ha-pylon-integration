# Pylontech Serial Integration for Home Assistant

Fork releases use `<upstream-version>+piposa.<revision>`. Version
`1.2.3+piposa.1` includes upstream 1.2.3 and this fork's RS485 extensions.

[![Open Marketplace Repository on My HA](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=piposa&repository=ha-pylon-integration&category=integration)
[![Add Integration to My HA](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=pylontech_serial)

Monitor a Pylontech battery stack in Home Assistant over its serial console or through a low-voltage RS485 gateway.

## Features
- **Serial console** reads module data through the master battery's console port.
- **RS485 low-voltage mode** discovers modules and reads each cell voltage, temperature position, and BMS diagnostics.
- **Home Assistant Native**: No MQTT or Docker containers required.
- **Energy Dashboard** support in console mode includes calculated energy sensors in kWh.
- **Per-Battery Monitoring**: Voltage, Current, SOC, Temperature, and Status for each module.
- **Console capacity settings** let you tune the capacity of each battery module (Number entity) to accurately compute total stored energy.
- **Diagnostics & Raw Data**: Track system health (SOH), cycle count, firmware version, and view raw serial responses for debugging.
- **Console time synchronization** can sync the BMS clock automatically or manually.
- **Console commands** can be sent using the Home Assistant action.

> [!WARNING]
> **Disclaimer:** This integration interacts directly with your hardware. Incorrect configuration or usage could potentially cause damage to your batteries or connected devices. The creators and contributors of this integration take **no responsibility** for any damage, data loss, or other issues that may arise from using this software. Use at your own risk.

> [!IMPORTANT]
> This integration is not affiliated with or endorsed by Pylontech.
> It is a completely independent project, backed up by the community, and based on official documentation, commands, and reverse engineering.

> [!NOTE]
> **USB Auto-Discovery**: Currently, **only** the Prolic PL2303 scanner (VID `067B`, PID `2303`) is supported for auto-discovery. If you have a different adapter, it will not be automatically detected, but you can still manually select the port during configuration.
>
> To add auto-discovery support for your device, please see [CONTRIBUTING.md](CONTRIBUTING.md).

> [!NOTE]
> **Disclaimer:** this project has been generated mainly by AI. Even though it has been reviewed and tested by a professional programmer, I feel like it's important to disclose this fact.

## Installation

### Via the Marketplace (Recommended)

Starting with Home Assistant **2026.11**, HACS is called the **Marketplace**.

[![Open Marketplace Repository on My HA](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=piposa&repository=ha-pylon-integration&category=integration)

1.  Ensure you have the [Marketplace](https://hacs.xyz/) (HACS) installed.
2.  Go to **Marketplace > Integrations**.
3.  Click the **3 dots** (top right) > **Custom repositories**.
4.  Add the URL of this repository.
5.  Category: **Integration**.
6.  Click **Add**, then find and install **Pylontech Serial**.
7.  Restart Home Assistant.

> [!NOTE]
> **Home Assistant earlier than 2026.11:** the Marketplace is named **HACS** there. Follow the same steps, using **HACS > Integrations** in step 2.

### Manual Installation

1. **Locate your configuration directory**: Find your Home Assistant `config` folder (where `configuration.yaml` lives).
2. **Create custom_components**: If it doesn't exist, create a folder named `custom_components` inside your `config` folder.
3. **Copy files**: Copy the `pylontech_serial` folder from `custom_components/` in this repository to your Home Assistant's `custom_components/` folder.
   - Resulting path: `/config/custom_components/pylontech_serial/`
4. **Restart Home Assistant**: This is crucial for HA to recognize the new component.

## Configuration

[![Add Integration to My HA](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=pylontech_serial)

1. Open **Settings → Devices & Services → Add Integration → Pylontech Serial**.
2. Choose the serial port. A detected adapter is preselected when it can be identified unambiguously. Use **Enter manually** in the port selector to type a local path or network URL.
3. Set the baud rate (default 115200) and polling interval **in seconds** (default 15).
4. Enable **RS485 low-voltage protocol** if the gateway is attached to the BMS RS485 bus. Leave it off for the text console.
5. Save. Changing an existing entry's options reloads the integration automatically.

### RS485 gateways

Use `socket://HOST:PORT` for a raw TCP listener or `rfc2217://HOST:PORT` for a
listener that supports RFC 2217. With raw TCP, set the serial baud rate on the
gateway. Saved gateway URLs appear in the same port selector as local adapters.

The integration finds the first responding stack and its numbered modules at
startup. Each module has its own Home Assistant device with cell voltages,
measured temperatures and pack values. Alarms, limits, identification and
communication readings appear under **Diagnostic**. Home Assistant defaults to
three decimal places for voltage values in volts and one for temperatures in
degrees Celsius. See [RS485 protocol notes](docs.md#rs485-low-voltage-mode).

### Battery Capacity Configuration
In console mode, the integration provides a **Number Entity** for *each* detected battery module. Once the integration is added, navigate to the device page for each module to adjust its capacity (in kWh). This ensures that the integration accurately calculates the total stored energy across batteries of different sizes.

### Hardware Configuration
Ensure your battery DIP switches are configured correctly for communication. For US2000/US3000, **all DIP switches OFF** selects the default baud rate of **115200**.

![DIP Switches](img/dip-switches.jpg)
*Pylontech US2000 with all DIP switches OFF*

## Energy Dashboard Setup

To track battery usage in the Energy Dashboard in console mode, add these entities to your battery system.

1. Go to **Settings** > **Dashboards** > **Energy**.
2. Find the **Battery Systems** section and click **Add Battery System**.
3. For **Energy going in to the battery**, select: `sensor.pylontech_stack_system_energy_charged`
4. For **Energy coming out of the battery**, select: `sensor.pylontech_stack_system_energy_discharged`
5. Click **Save**.

## Troubleshooting
- **Console setup fails with `Did not receive valid 'pwr' response`**. Check the port and verify that the cable is plugged into the master battery's console. If the gateway connects to the BMS RS485 bus, enable RS485 low-voltage mode.
- **Permissions**: If running Home Assistant Core in Docker (not OS), ensure the device is passed through (`--device /dev/ttyUSB0`).
