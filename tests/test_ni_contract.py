"""Contract tests with fake API objects, NOT NI driver or physical-hardware tests."""
from types import SimpleNamespace as NS
import pytest
from tankdaq.ni_backend import NIAnalog,NICounter,verify_inventory

class FakeChannel:
    pass

class FakeAI:
    def __init__(self):self.rtd=[];self.voltage=[]
    def add_ai_rtd_chan(self,physical_channel,name_to_assign_to_channel='',min_val=0.,max_val=100.,
                        units=None,rtd_type=None,resistance_config=None,current_excit_source=None,
                        current_excit_val=0.,r_0=100.):
        c=FakeChannel();self.rtd.append((locals().copy(),c));return c
    def add_ai_voltage_chan(self,physical_channel,name_to_assign_to_channel='',terminal_config=None,
                            min_val=-10.,max_val=10.,units=None):
        self.voltage.append(locals().copy());return FakeChannel()

class FakeCI:
    def __init__(self):self.calls=[]
    def add_ci_count_edges_chan(self,counter,name_to_assign_to_channel='',edge=None,initial_count=0,count_direction=None):
        c=FakeChannel();self.calls.append((locals().copy(),c));return c

class FakeStream:
    def __init__(self):self.input_buf_size=1000;self.logs=[]
    def configure_logging(self,file_path,logging_mode=None,group_name='',operation=None):
        self.logs.append(locals().copy())

class FakeTiming:
    samp_clk_src='OnboardClock'
    def cfg_samp_clk_timing(self,rate,sample_mode=None,samps_per_chan=1000):
        self.samp_clk_rate=rate;self.mode=sample_mode

class FakeTask:
    def __init__(self,new_task_name=''):
        self.name=new_task_name;self.ai_channels=FakeAI();self.ci_channels=FakeCI()
        self.timing=FakeTiming();self.in_stream=FakeStream();self.closed=False;self.controls=[]
    def control(self,action):self.controls.append(action)
    def close(self):self.closed=True

@pytest.fixture
def fake_api(monkeypatch):
    tasks=[]
    def create(new_task_name=''):
        t=FakeTask(new_task_name);tasks.append(t);return t
    c=NS(TemperatureUnits=NS(DEG_C='DEG_C'),RTDType=NS(PT_3851='PT_3851'),
         ResistanceConfiguration=NS(FOUR_WIRE='FOUR_WIRE'),ExcitationSource=NS(INTERNAL='INTERNAL'),
         ADCTimingMode=NS(HIGH_RESOLUTION='HIGH_RESOLUTION'),TerminalConfiguration=NS(DIFF='DIFF'),
         VoltageUnits=NS(VOLTS='VOLTS'),AcquisitionType=NS(CONTINUOUS='CONTINUOUS'),
         OverwriteMode=NS(DO_NOT_OVERWRITE_UNREAD_SAMPLES='NO_OVERWRITE'),
         LoggingMode=NS(LOG_AND_READ='LOG_AND_READ'),LoggingOperation=NS(CREATE='CREATE'),
         TaskMode=NS(TASK_COMMIT='COMMIT'),Edge=NS(RISING='RISING'),CountDirection=NS(COUNT_UP='COUNT_UP'))
    monkeypatch.setattr('tankdaq.ni_backend.api',lambda:(NS(Task=create),c,lambda stream:NS(stream=stream),None))
    return tasks

def test_rtd_contract(rig,tmp_path,fake_api):
    w=NIAnalog('rtd',rig,tmp_path);w.prepare();task=fake_api[-1]
    assert len(task.ai_channels.rtd)==4
    for args,ch in task.ai_channels.rtd:
        assert args['resistance_config']=='FOUR_WIRE'
        assert args['rtd_type']=='PT_3851'
        assert args['current_excit_val']==.001
        assert args['r_0']==100.
        assert ch.ai_adc_timing_mode=='HIGH_RESOLUTION'
    assert w.rate==1.
    assert task.in_stream.logs[0]['operation']=='CREATE'
    assert task.in_stream.auto_start is False
    w.close();assert task.closed

def test_analog_contract(rig,tmp_path,fake_api):
    w=NIAnalog('analog',rig,tmp_path);w.prepare();task=fake_api[-1]
    assert len(task.ai_channels.voltage)==7
    assert all(x['terminal_config']=='DIFF' for x in task.ai_channels.voltage)
    assert all(x['min_val']==-10. and x['max_val']==10. for x in task.ai_channels.voltage)
    assert task.in_stream.over_write=='NO_OVERWRITE'
    assert task.in_stream.logs[0]['logging_mode']=='LOG_AND_READ'
    w.close()

def test_counter_contract(rig,fake_api):
    w=NICounter(rig);w.prepare()
    assert len(w.tasks)==2
    args0,ch0=w.tasks[0].ci_channels.calls[0]
    assert args0['counter']=='cDAQ1Mod3/ctr0' and ch0.ci_count_edges_term=='/cDAQ1Mod3/PFI0'
    assert args0['initial_count']==0 and args0['count_direction']=='COUNT_UP'
    assert w.tasks[0].in_stream.auto_start is False
    args1,ch1=w.tasks[1].ci_channels.calls[0]
    assert args1['counter']=='cDAQ1Mod3/ctr1' and ch1.ci_count_edges_term=='/cDAQ1Mod3/PFI1'
    assert args1['initial_count']==0 and args1['count_direction']=='COUNT_UP'
    assert w.tasks[1].in_stream.auto_start is False
    w.close()

def make_inventory(rig):
    hw=rig['hardware'];devices=[]
    for key,model in [('chassis','9173'),('rtd_module','9217'),('analog_module','9204'),('counter_module','9401')]:
        devices.append(dict(name=hw[key],product_type='NI '+model,is_simulated=False,
                            ai_physical_chans=[],ci_physical_chans=[],terminals=[]))
    devices[1]['ai_physical_chans']=[x['physical'] for x in rig['rtd']['channels']]
    devices[2]['ai_physical_chans']=[x['physical'] for x in rig['analog']['channels']]
    devices[3]['ci_physical_chans']=[c['counter_channel'] for c in rig['counter']['channels']]
    devices[3]['terminals']=[c['pulse_terminal'] for c in rig['counter']['channels']]
    return {'devices':devices}

def test_inventory_accepts_configured_resources(rig):verify_inventory(rig,make_inventory(rig))

def test_inventory_rejects_ni_max_simulation(rig):
    info=make_inventory(rig);info['devices'][1]['is_simulated']=True
    with pytest.raises(RuntimeError,match='simulated devices'):verify_inventory(rig,info)

def test_inventory_rejects_wrong_counter_route(rig):
    info=make_inventory(rig);info['devices'][3]['ci_physical_chans']=['cDAQ1Mod3/ctr0']
    with pytest.raises(RuntimeError,match='not enumerated'):verify_inventory(rig,info)

def test_inventory_rejects_wrong_module(rig):
    info=make_inventory(rig);info['devices'][2]['product_type']='NI 9205'
    with pytest.raises(RuntimeError,match='expected model'):verify_inventory(rig,info)
