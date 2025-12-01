from typing import Callable

from modules import config_manager


class ExpertMode:
    def __init__(self, config: dict, on_change: Callable[[bool], None]):
        self.config = config
        self.enabled = False
        self._on_change = on_change

    def toggle(self, pin: str) -> bool:
        if self.enabled:
            self.enabled = False
        else:
            expected_pin = str(self.config.get("expert_pin", config_manager.DEFAULT_CONFIG["expert_pin"]))
            self.enabled = pin == expected_pin
        self._on_change(self.enabled)
        return self.enabled
