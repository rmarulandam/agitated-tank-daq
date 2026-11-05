import copy
import math
import pytest
from tankdaq.config import validate,ConfigError
from tankdaq.scaling import convert_voltage,FlowWindow

def test_templates_valid(demo,rig,pilot_demo):
    validate(demo);validate(rig);validate(pilot_demo)

def test_pilot_demo_hardware_ready(pilot_demo):
    validate(pilot_demo,backend='ni',acknowledge_wiring=True)

def test_simulation_cannot_run_hardware(demo):
    with pytest.raises(ConfigError,match='simulation_only'):
        validate(demo,backend='ni',acknowledge_wiring=True)

def test_acknowledgement_required(rig):
    with pytest.raises(ConfigError,match='acknowledge-wiring'):
        validate(rig,backend='ni',raw_only=True)

def test_wiring_checks_required(rig):
    with pytest.raises(ConfigError,match='electrical checks'):
        validate(rig,backend='ni',raw_only=True,acknowledge_wiring=True)

def test_raw_commissioning_allowed(rig):
    rig['checks']={k:True for k in rig['checks']}
    validate(rig,backend='ni',raw_only=True,acknowledge_wiring=True)

def test_scaled_hardware_requires_confirmation(rig):
    rig['checks']={k:True for k in rig['checks']}
    with pytest.raises(ConfigError,match='Unconfirmed scales'):
        validate(rig,backend='ni',acknowledge_wiring=True)

@pytest.mark.parametrize('key,value',[('analog_hz',0),('rtd_hz',float('nan')),('counter_poll_hz',True),('queue_blocks',1.5)])
def test_invalid_sampling(demo,key,value):
    demo['sampling'][key]=value
    with pytest.raises(ConfigError):validate(demo)

def test_wrong_differential_pair(demo):
    demo['analog']['channels'][0]['negative_input']='ai1'
    with pytest.raises(ConfigError,match='differential pairs'):validate(demo)

def test_no_guessed_signal_range(demo):
    demo['analog']['channels'][7]['scale']['signal_range_v']=None
    with pytest.raises(ConfigError,match='signal_range_v'):validate(demo)

def test_unknown_top_level_key(demo):
    demo['samplng']={}
    with pytest.raises(ConfigError):validate(demo)

def test_scales_outside_daq_range(demo):
    demo['analog']['channels'][0]['daq_range_v']=[-1.,1.]
    with pytest.raises(ConfigError,match='exceeds DAQ'):validate(demo)

@pytest.mark.parametrize('voltage,expected',[(1.,0.),(3.,50.),(5.,100.)])
def test_current_scale_endpoints(demo,voltage,expected):
    ch=demo['analog']['channels'][3]
    assert convert_voltage(voltage,ch,raw_only=False).value==pytest.approx(expected)

@pytest.mark.parametrize('voltage,fraction',[(0.,0.),(5.,.5),(10.,1.)])
def test_voltage_linear_scale(demo,voltage,fraction):
    ch_power=demo['analog']['channels'][7]
    assert convert_voltage(voltage,ch_power,raw_only=False).value==pytest.approx(fraction*1500.0)

def test_measured_shunt_is_used(demo):
    ch=demo['analog']['channels'][3];ch['scale']['shunt_ohm']=249.
    assert convert_voltage(.012*249.,ch,raw_only=False).value==pytest.approx(50.)

def test_scale_no_clipping(demo):
    result=convert_voltage(5.4,demo['analog']['channels'][3],raw_only=False)
    assert result.value>100.
    assert 'OUTSIDE_NOMINAL_SIGNAL' in result.quality

def test_unconfirmed_returns_null(rig):
    assert convert_voltage(3.,rig['analog']['channels'][3],raw_only=False).value is None

def test_raw_only_never_returns_scaled_value(demo):
    result=convert_voltage(3.,demo['analog']['channels'][3],raw_only=True)
    assert result.value is None and 'RAW_ONLY' in result.quality

def test_nonfinite_voltage(demo):
    result=convert_voltage(float('nan'),demo['analog']['channels'][3],raw_only=False)
    assert result.value is None and result.quality=='NONFINITE_INPUT'

def update(f,t,n,confirmed=True,raw=False):
    return f.update(t,n,scale_confirmed=confirmed,raw_only=raw,valid_range=[5.,150.])

def test_flow_frequency_and_resolution():
    f=FlowWindow(10.,.5)
    update(f,0.,0)
    r=update(f,10.,150)
    assert r['frequency_hz']==15.
    assert r['value']==30.
    assert r['flow_l_min']==30.
    assert r['one_count_resolution']==pytest.approx(.2)
    assert r['one_count_resolution_l_min']==pytest.approx(.2)

def test_counter_rollover():
    f=FlowWindow(1.,.5)
    update(f,0.,2**32-3)
    r=update(f,1.,2)
    assert r['window_counts']==5 and r['value']==10.

def test_counter_zero_and_warmup():
    f=FlowWindow(10.,.5)
    assert update(f,0.,0)['frequency_hz'] is None
    r=update(f,2.,0)
    assert r['value']==0.
    assert 'WARMUP' in r['quality'] and 'SIGNAL_LOSS' in r['quality']

def test_counter_unconfirmed_keeps_frequency():
    f=FlowWindow(1.,.5);update(f,0.,0)
    r=update(f,1.,10,confirmed=False)
    assert r['frequency_hz']==10. and r['value'] is None

def test_counter_uses_actual_time():
    f=FlowWindow(1.,.5);update(f,.123,0)
    r=update(f,1.323,12)
    assert r['frequency_hz']==pytest.approx(10.)

def test_counter_monotonic_enforced():
    f=FlowWindow(1.,.5);update(f,1.,0)
    with pytest.raises(ValueError):update(f,1.,1)

def test_rolling_window_bounded():
    f=FlowWindow(10.,.5)
    for i in range(1000):r=update(f,float(i),i*15)
    assert len(f.history)<=12
    assert r['value']==30.

def test_custom_channel_names_accepted(demo):
    custom_rtd = ["t_inlet_c", "t_outlet_c", "t_top_c", "t_bottom_c"]
    for i, name in enumerate(custom_rtd):
        demo["rtd"]["channels"][i]["name"] = name
    custom_analog = ["t_air_1_c", "rh_air_1", "t_air_2_c", "rh_air_2", "p_baro_pa", "humidity_pct", "dp_duct_pa", "motor_pwr_w"]
    for i, name in enumerate(custom_analog):
        demo["analog"]["channels"][i]["name"] = name
    custom_counters = ["q_in_l_min", "q_out_l_min", "shaft_rpm"]
    for i, name in enumerate(custom_counters):
        demo["counter"]["channels"][i]["name"] = name
    validate(demo)

def test_rtd_count_must_be_four(demo):
    demo["rtd"]["channels"] = demo["rtd"]["channels"][:3]
    with pytest.raises(ConfigError, match="Four RTD channels are required"):
        validate(demo)

def test_analog_count_must_be_eight(demo):
    demo["analog"]["channels"] = demo["analog"]["channels"][:7]
    with pytest.raises(ConfigError, match="Eight analog channels are required"):
        validate(demo)

def test_counter_count_must_be_three(demo):
    demo["counter"]["channels"] = demo["counter"]["channels"][:2]
    with pytest.raises(ConfigError, match="Three counter channels are required"):
        validate(demo)

def test_duplicate_counter_physical_rejected(demo):
    demo["counter"]["channels"][1]["physical"] = "cDAQ1Mod3/ctr0"
    with pytest.raises(ConfigError, match="Counter physical channels must be unique"):
        validate(demo)

def test_invalid_channel_name_format(demo):
    demo["rtd"]["channels"][0]["name"] = "123_invalid"
    with pytest.raises(ConfigError, match=r"rtd\[0\]\.name"):
        validate(demo)

def test_duplicate_channel_name_rejected(demo):
    demo["rtd"]["channels"][0]["name"] = "duplicate_name"
    demo["rtd"]["channels"][1]["name"] = "duplicate_name"
    with pytest.raises(ConfigError, match="unique"):
        validate(demo)


def test_storage_auto_export_boolean_check(demo):
    demo["storage"]["auto_export_csv"] = "yes"
    with pytest.raises(ConfigError, match="storage.auto_export_csv"):
        validate(demo)

    demo["storage"]["auto_export_csv"] = True
    demo["storage"]["auto_export_parquet"] = 123
    with pytest.raises(ConfigError, match="storage.auto_export_parquet"):
        validate(demo)


def test_external_rpm_section_rejected(demo):
    demo["external"] = {"impeller_rpm": 100, "method": "manual"}
    with pytest.raises(ConfigError, match="Top-level keys"):
        validate(demo)
