"""Custom Locust spawn shape — users arrive in configurable waves."""

import os

import yaml
from locust import LoadTestShape


def _load_config():
    """Load wave + timing config from the same YAML the sim uses."""
    config_path = os.environ.get("NEURO_SIM_CONFIG", "config/prestage.yaml")
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
        raw = cfg.get("waves", [[5, 30]])
        waves = [(w[0], w[1]) for w in raw]
        # Hold time after last wave (seconds). 0 = stop immediately after waves.
        hold = cfg.get("simulation", {}).get("hold_after_waves", 120)
        return waves, hold
    except Exception:
        return [(5, 30)], 120


_WAVES, _HOLD = _load_config()


class WaveShape(LoadTestShape):
    """Gradually ramps users in waves from config, then holds for hold_after_waves seconds.

    Config example:
      waves:
        - [5, 5]      # 5 users over 5s
        - [10, 30]    # then 10 more over 30s
      simulation:
        hold_after_waves: 120  # hold at max users for 120s, then stop
    """

    def tick(self):
        run_time = self.get_run_time()
        elapsed = 0
        total_users = 0

        for users_to_add, duration in _WAVES:
            total_users += users_to_add
            elapsed += duration
            if run_time < elapsed:
                spawn_rate = max(users_to_add / duration, 0.5)
                return total_users, spawn_rate

        # All waves done — hold at max for _HOLD seconds, then stop
        if run_time < elapsed + _HOLD:
            return total_users, 1

        # Time's up — return None to stop
        return None
