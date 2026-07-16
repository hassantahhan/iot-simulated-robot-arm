"""Readings enricher for the SO-ARM101 simulator.

Generates simulated physical signals (velocity, torque, temperature)
from raw joint positions — mimicking what real servo sensors would report.
"""

import time
import random

class SimulatedSignals:
    """Produces realistic sensor readings from raw joint angles.

    Real servos report position, velocity, torque (current draw),
    and temperature. This class derives those signals from position
    deltas and simple physics approximations.
    """

    def __init__(self, joint_names: list[str]):
        self._last_positions = {name: 0.0 for name in joint_names}
        self._last_time = time.time()
        self._temperatures = {name: 25.0 for name in joint_names}
        self._cumulative_work = {name: 0.0 for name in joint_names}

    def generate(self, joint_positions: dict[str, float]) -> dict:
        """Generate a full readings payload from current joint positions.

        Args:
            joint_positions: Dict of joint_name -> angle in radians.

        Returns:
            Complete readings dict with timestamp and per-joint sensor values.
        """
        now = time.time()
        dt = max(now - self._last_time, 0.001)
        self._last_time = now

        joints_readings = {}
        for name, position in joint_positions.items():
            prev = self._last_positions.get(name, position)
            velocity = (position - prev) / dt
            self._last_positions[name] = position

            # Torque approximation: proportional to velocity + base load
            torque = abs(velocity) * 0.05 + random.gauss(0.1, 0.02)
            torque = max(0.0, torque)

            # Temperature: rises with work, slowly cools toward ambient (25C)
            work = abs(velocity) * dt
            self._cumulative_work[name] += work
            ambient = 25.0
            cooling_rate = 0.01
            heating_rate = 0.003
            self._temperatures[name] += work * heating_rate
            self._temperatures[name] -= (self._temperatures[name] - ambient) * cooling_rate
            self._temperatures[name] += random.gauss(0, 0.05)  # sensor noise
            self._temperatures[name] = max(ambient, self._temperatures[name])

            joints_readings[name] = {
                "position": round(position, 3),
                "velocity": round(velocity, 3),
                "torque": round(torque, 4),
                "temperature": round(self._temperatures[name], 2),
            }

        return {
            "timestamp": now,
            "device_id": "so-arm101-simulator",
            "joints": joints_readings,
        }
