"""Load and validate configuration without importing the NI driver."""
from __future__ import annotations
import copy
import math
import re
from pathlib import Path
from typing import Any
import yaml

class ConfigError(ValueError):
    """Invalid or insufficiently confirmed experiment configuration."""

# Fail closed on misspelled top-level sections. Each signal's identity is fixed.
ROOT_KEYS = {"schema_version", "simulation_only", "run", "hardware", "checks",
             "sampling", "rtd", "analog", "counter", "storage", "external"}
RTD_NAMES = ("t_air_in_c", "t_air_out_c", "t_water_upper_c", "t_water_bulk_c")
ANALOG_NAMES = ("t_ambient_c", "rh_ambient_pct", "p_atm_pa", "p_water_in_pa",
                "p_water_out_pa", "dp_air_duct_pa", "v_air_m_s")
CHECK_NAMES = ("wiring_verified", "sensor_supplies_verified", "rtd_curve_verified",
               "hall_logic_verified")

def number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label} must be a number, not {value!r}")
    n = float(value)
    if not math.isfinite(n) or (positive and n <= 0):
        raise ConfigError(f"{label} must be finite" + (" and > 0" if positive else ""))
    return n

def pair(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigError(f"{label} must be [minimum, maximum]")
    lo, hi = (number(v, label) for v in value)
    if hi <= lo:
        raise ConfigError(f"{label}: maximum must exceed minimum")
    return lo, hi

def _boolean(value: Any, label: str) -> None:
    if type(value) is not bool:
        raise ConfigError(f"{label} must be true or false")

def validate(cfg: dict[str, Any], *, backend: str = "sim", raw_only: bool = False,
             acknowledge_wiring: bool = False) -> None:
    try:
        if not isinstance(cfg, dict) or set(cfg) != ROOT_KEYS:
            raise ConfigError(f"Top-level keys must be exactly {sorted(ROOT_KEYS)}")
        if cfg["schema_version"] != 1:
            raise ConfigError("Only schema_version: 1 is supported")
        _boolean(cfg["simulation_only"], "simulation_only")
        if backend not in {"sim", "ni"}:
            raise ConfigError("backend must be sim or ni")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", cfg["run"]["label"]):
            raise ConfigError("run.label: use 1-50 ASCII letters, digits, '_' or '-'")
        for key in CHECK_NAMES:
            _boolean(cfg["checks"][key], f"checks.{key}")
        hw = cfg["hardware"]
        for key in ("chassis", "rtd_module", "analog_module", "counter_module"):
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", hw[key]):
                raise ConfigError(f"hardware.{key}: invalid DAQmx device name")
        if len({hw[k] for k in ("rtd_module", "analog_module", "counter_module")}) != 3:
            raise ConfigError("RTD, analog and counter modules must be distinct")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*/ctr[0-9]+", hw["counter_channel"]):
            raise ConfigError("Invalid counter_channel; use a name from 'tankdaq devices'")
        if not re.fullmatch(r"/[A-Za-z][A-Za-z0-9_]*/PFI[0-9]+", hw["pulse_terminal"]):
            raise ConfigError("pulse_terminal must be an explicit /device/PFIx route")
        sampling = cfg["sampling"]
        for key in ("rtd_hz", "analog_hz", "counter_poll_hz", "flow_window_s",
                    "buffer_seconds", "idle_timeout_s"):
            number(sampling[key], f"sampling.{key}", positive=True)
        for key in ("max_block_samples", "queue_blocks"):
            n = sampling[key]
            if isinstance(n, bool) or not isinstance(n, int) or n < 1:
                raise ConfigError(f"sampling.{key} must be a positive integer")
        if sampling["flow_window_s"] < 1.0 / sampling["counter_poll_hz"]:
            raise ConfigError("flow_window_s must be at least one counter polling interval")
        if sampling["idle_timeout_s"] < 3.0 / min(sampling["rtd_hz"], sampling["analog_hz"]):
            raise ConfigError("idle_timeout_s must allow at least three slowest sample periods")
        if cfg["rtd"]["type"] not in {"PT_3851", "PT_3750", "PT_3911", "PT_3916", "PT_3920", "PT_3928"}:
            raise ConfigError("Unsupported RTD curve. Custom CVD coefficients are not implemented")
        if cfg["rtd"]["adc_mode"] not in {"HIGH_RESOLUTION", "HIGH_SPEED"}:
            raise ConfigError("rtd.adc_mode must be HIGH_RESOLUTION or HIGH_SPEED")
        number(cfg["rtd"]["r0_ohm"], "rtd.r0_ohm", positive=True)
        if float(cfg["rtd"]["excitation_a"]) != 0.001:
            raise ConfigError("This NI-9217 design requires internal excitation_a: 0.001")
        pair(cfg["rtd"]["measurement_range_c"], "rtd.measurement_range_c")
        rtd = cfg["rtd"]["channels"]
        analog = cfg["analog"]["channels"]
        if cfg["analog"]["terminal_configuration"] != "DIFFERENTIAL":
            raise ConfigError("This design requires DIFFERENTIAL analog inputs")
        if len(rtd) != 4 or tuple(c["name"] for c in rtd) != RTD_NAMES:
            raise ConfigError(f"Four RTD channels in this order are required: {RTD_NAMES}")
        if len(analog) != 7 or tuple(c["name"] for c in analog) != ANALOG_NAMES:
            raise ConfigError(f"Seven analog channels in this order are required: {ANALOG_NAMES}")
        for i, ch in enumerate(rtd):
            if ch["physical"] != f"{hw['rtd_module']}/ai{i}":
                raise ConfigError("RTD physical channels must be ai0 through ai3 on rtd_module")
            for key in ("gain", "offset_c"):
                number(ch[key], f"{ch['name']}.{key}")
            if not ch["raw_name"].endswith("_raw_c"):
                raise ConfigError("RTD raw names must end in _raw_c")
        for i, ch in enumerate(analog):
            if ch["physical"] != f"{hw['analog_module']}/ai{i}" or ch["negative_input"] != f"ai{i+8}":
                raise ConfigError("NI-9204 differential pairs must be ai0/ai8 through ai6/ai14")
            lo, hi = pair(ch["daq_range_v"], f"{ch['name']}.daq_range_v")
            if (lo, hi) not in {(-10., 10.), (-5., 5.), (-1., 1.), (-0.2, 0.2)}:
                raise ConfigError("Use an NI-9204 supported symmetric voltage range")
            s = ch["scale"]
            _boolean(s["confirmed"], f"{ch['name']}.scale.confirmed")
            if s["kind"] not in {"current_loop", "voltage_linear"}:
                raise ConfigError("scale.kind must be current_loop or voltage_linear")
            if s["kind"] == "current_loop":
                number(s["shunt_ohm"], f"{ch['name']}.shunt_ohm", positive=True)
                pair(s["signal_range_ma"], "signal_range_ma")
            elif s["signal_range_v"] is not None:
                pair(s["signal_range_v"], "signal_range_v")
            if s["engineering_range"] is not None:
                pair(s["engineering_range"], "engineering_range")
            number(s["post_gain"], "post_gain")
            number(s["post_offset"], "post_offset")
            if s["confirmed"]:
                if s["engineering_range"] is None or not s["calibration_id"]:
                    raise ConfigError(f"{ch['name']}: confirmed scale requires range and calibration_id")
                if s["kind"] == "voltage_linear" and s["signal_range_v"] is None:
                    raise ConfigError(f"{ch['name']}: confirmed voltage scale requires signal_range_v")
                if s["kind"] == "current_loop":
                    v0, v1 = [x * s["shunt_ohm"] / 1000 for x in s["signal_range_ma"]]
                else:
                    v0, v1 = s["signal_range_v"]
                if v0 < lo or v1 > hi:
                    raise ConfigError(f"{ch['name']}: transmitter range exceeds DAQ range")
        all_names = [c["name"] for c in rtd + analog] + [c["raw_name"] for c in rtd + analog]
        if len(all_names) != len(set(all_names)):
            raise ConfigError("Engineering names and raw names must be unique")
        cs = cfg["counter"]
        number(cs["hz_per_l_min"], "counter.hz_per_l_min", positive=True)
        pair(cs["valid_flow_l_min"], "counter.valid_flow_l_min")
        _boolean(cs["calibration_confirmed"], "counter.calibration_confirmed")
        if cs["calibration_confirmed"] and not cs["calibration_id"]:
            raise ConfigError("Counter calibration_id is required when confirmed")
        if cs["edge"] not in {"RISING", "FALLING"}:
            raise ConfigError("counter.edge must be RISING or FALLING")
        if cs["bits"] != 32:
            raise ConfigError("This chassis design uses a 32-bit counter")
        for key in ("tdms",):
            _boolean(cfg["storage"][key], "storage." + key)
        number(cfg["storage"]["min_free_mb"], "storage.min_free_mb", positive=True)
        number(cfg["storage"]["commit_interval_s"], "storage.commit_interval_s", positive=True)
        ext = cfg["external"]
        if ext["impeller_rpm"] is not None:
            if number(ext["impeller_rpm"], "external.impeller_rpm") < 0 or not ext["method"]:
                raise ConfigError("Externally entered RPM requires nonnegative RPM and a method")
        if ext["uncertainty_rpm"] is not None and number(ext["uncertainty_rpm"], "uncertainty_rpm") < 0:
            raise ConfigError("uncertainty_rpm cannot be negative")
        if backend == "ni":
            if cfg["simulation_only"]:
                raise ConfigError("A simulation_only configuration can never operate NI hardware")
            if not acknowledge_wiring:
                raise ConfigError("Hardware acquisition requires --acknowledge-wiring")
            missing = [key for key in CHECK_NAMES if not cfg["checks"][key]]
            if missing:
                raise ConfigError("Complete the electrical checks, then set true: " + ", ".join(missing))
            if not raw_only:
                pending = [c["name"] for c in analog if not c["scale"]["confirmed"]]
                if not cs["calibration_confirmed"]:
                    pending.append("q_water_l_min")
                if pending:
                    raise ConfigError("Unconfirmed scales: " + ", ".join(pending) + ". Use --raw-only for commissioning")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ConfigError(f"Missing or malformed configuration field: {exc}") from exc

def load(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig") as fh:
        cfg = yaml.safe_load(fh)
    validate(cfg)
    return cfg

def copy_config(cfg: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(cfg)
