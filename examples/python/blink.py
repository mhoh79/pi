"""
blink.py - GPIO blink example using gpiozero with automatic mock fallback.

On a real Raspberry Pi the physical LED wired to GPIO 17 will blink.
Inside a devcontainer (no /sys/class/gpio) the mock pin factory is used
so the script still runs and prints meaningful output.
"""

from __future__ import annotations

import os
import sys
import time

# ---------------------------------------------------------------------------
# Pin factory selection
# ---------------------------------------------------------------------------
GPIO_SYSFS_PATH = "/sys/class/gpio"

def _configure_pin_factory() -> bool:
    """Return True if running in simulation mode (mock pin factory)."""
    simulated = not os.path.exists(GPIO_SYSFS_PATH)
    if simulated:
        os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")
    return simulated


SIMULATED = _configure_pin_factory()

# gpiozero must be imported *after* the environment variable is set.
try:
    from gpiozero import LED
    from gpiozero.pins.mock import MockFactory  # noqa: F401 (imported for type info)
except ImportError as exc:
    sys.exit(
        f"gpiozero is not installed: {exc}\n"
        "Install it with:  pip install gpiozero"
    )

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LED_PIN     = 17
BLINK_COUNT = 5
ON_TIME     = 0.5   # seconds
OFF_TIME    = 0.5   # seconds

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    led = LED(LED_PIN)

    # Determine the active pin factory for informational output.
    factory_type = type(led.pin_factory).__name__

    print("Raspberry Pi GPIO blink example (gpiozero)")
    print(f"Pin factory : {factory_type}")
    print(f"Simulation  : {'yes (no /sys/class/gpio found)' if SIMULATED else 'no (real hardware)'}")
    print(f"LED pin     : GPIO {LED_PIN}")
    print(f"Blink count : {BLINK_COUNT}")
    print()

    for i in range(1, BLINK_COUNT + 1):
        print(f"Blink {i}/{BLINK_COUNT} -> ON")
        led.on()
        time.sleep(ON_TIME)

        print(f"Blink {i}/{BLINK_COUNT} -> OFF")
        led.off()
        time.sleep(OFF_TIME)

    led.close()
    print(f"\nDone. {BLINK_COUNT} blinks completed.")


if __name__ == "__main__":
    main()
