from __future__ import annotations
from dataclasses import dataclass, field
import time
from typing import Any
import numpy as np

@dataclass(frozen=True)
class Clock:
    epoch_ns: int
    mono_ns: int

    @classmethod
    def now(cls) -> 'Clock':
        before = time.perf_counter_ns()
        epoch = time.time_ns()
        after = time.perf_counter_ns()
        return cls(epoch, (before+after)//2)

    def elapsed(self) -> float:
        return (time.perf_counter_ns()-self.mono_ns)/1e9

    def epoch_for(self, t_rel: float) -> int:
        return self.epoch_ns + round(t_rel*1e9)

@dataclass
class AnalogBlock:
    stream: str
    first_index: int
    rate_hz: float
    t0_est_s: float
    read_rel_s: float
    values: np.ndarray
    simulated: bool

@dataclass
class CounterPoint:
    index: int
    channel: str
    t_rel_s: float
    read_duration_s: float
    count: int
    simulated: bool

@dataclass
class StreamInfo:
    stream: str
    info: dict[str, Any]

@dataclass
class WorkerFault:
    stream: str
    message: str
    traceback: str

@dataclass
class WorkerOutcome:
    # A worker owns its task. The coordinator reads this only after joining it.
    name: str
    started: bool = False
    closed: bool = False
    samples_per_channel: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
