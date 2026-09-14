"""Transparent, unclipped engineering conversion and rolling pulse-count flow."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import math
from typing import Any

@dataclass(frozen=True)
class Scaled:
    value: float | None
    quality: str

def convert_voltage(v: float, channel: dict[str, Any], *, raw_only: bool) -> Scaled:
    if not math.isfinite(v):
        return Scaled(None, "NONFINITE_INPUT")
    lo, hi = channel["daq_range_v"]
    flags: list[str] = []
    if v <= lo + (hi-lo)*1e-5 or v >= hi - (hi-lo)*1e-5:
        flags.append("AT_DAQ_LIMIT")
    scale = channel["scale"]
    if scale["kind"] == "current_loop":
        signal = 1000.0*v / scale["shunt_ohm"]
        s0, s1 = scale["signal_range_ma"]
    else:
        signal = v
        limits = scale["signal_range_v"]
        if limits is None:
            return Scaled(None, "|".join(flags + ["RAW_ONLY" if raw_only else "UNCONFIRMED_SCALE"]))
        s0, s1 = limits
    # Diagnostic only: these are nominal signal endpoints, not safety thresholds.
    if signal < s0 or signal > s1:
        flags.append("OUTSIDE_NOMINAL_SIGNAL")
    if raw_only:
        return Scaled(None, "|".join(flags + ["RAW_ONLY"]))
    if not scale["confirmed"] or scale["engineering_range"] is None:
        return Scaled(None, "|".join(flags + ["UNCONFIRMED_SCALE"]))
    y0, y1 = scale["engineering_range"]
    value = y0 + (signal-s0)/(s1-s0)*(y1-y0)
    value = value*scale["post_gain"] + scale["post_offset"]
    # Deliberately no clipping: preserve overrange evidence.
    return Scaled(value, "|".join(flags) if flags else "OK")

class FlowWindow:
    """Unwrap a 32-bit counter and estimate average frequency over a rolling window.

    Counter readings are cumulative hardware counts. Their times are host-poll
    midpoints, not hardware-latched timestamps. A zero frequency cannot distinguish
    zero water flow from failed/disconnected pulse wiring.
    """
    def __init__(self, window_s: float, coefficient: float, bits: int = 32):
        self.window_s = window_s
        self.coefficient = coefficient
        self.modulus = 1 << bits
        self.last_raw: int | None = None
        self.total = 0
        self.history: deque[tuple[float, int]] = deque()

    def update(self, t: float, raw: int, *, scale_confirmed: bool,
               raw_only: bool, valid_range: list[float]) -> dict[str, Any]:
        if not 0 <= raw < self.modulus or not math.isfinite(t):
            raise ValueError("Counter reading/time is invalid")
        if self.history and t <= self.history[-1][0]:
            raise ValueError("Counter times must increase strictly")
        if self.last_raw is not None:
            self.total += (raw-self.last_raw) % self.modulus
        self.last_raw = raw
        self.history.append((t, self.total))
        # Keep the most recent point at/before t-window. Actual window is stored.
        target = t-self.window_s
        while len(self.history) > 2 and self.history[1][0] <= target:
            self.history.popleft()
        t0, n0 = self.history[0]
        dt, dn = t-t0, self.total-n0
        frequency = dn/dt if dt > 0 else None
        resolution = 1.0/(dt*self.coefficient) if dt > 0 and scale_confirmed and not raw_only else None
        flow = frequency/self.coefficient if frequency is not None and scale_confirmed and not raw_only else None
        flags: list[str] = []
        if dt < self.window_s - 1e-6:
            flags.append("WARMUP")
        if dt > 0 and dn == 0:
            flags.append("NO_PULSES_FLOW_OR_SIGNAL_LOSS")
        if raw_only:
            flags.append("RAW_ONLY")
        elif not scale_confirmed:
            flags.append("UNCONFIRMED_SCALE")
        if flow is not None and flow != 0 and not valid_range[0] <= flow <= valid_range[1]:
            flags.append("OUTSIDE_SENSOR_FLOW_RANGE")
        return dict(count_unwrapped=self.total, window_start_s=t0, window_end_s=t,
                    window_counts=dn, frequency_hz=frequency, flow_l_min=flow,
                    one_count_resolution_l_min=resolution,
                    quality="|".join(flags) if flags else "OK")
