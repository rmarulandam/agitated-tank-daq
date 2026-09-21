from pathlib import Path
import csv
import json
import queue
import sqlite3
import threading
import time
import numpy as np
import pytest
from tankdaq.models import Clock,AnalogBlock
from tankdaq.storage import RunStore
from tankdaq.runner import run
from tankdaq.data_tools import export_run,inspect_run,attach_rpm,add_note,watch
from tankdaq.backends import Worker

@pytest.fixture
def completed(tmp_path,demo,demo_path):
    demo['sampling']['rtd_hz']=5.
    folder,status=run(demo,demo_path,tmp_path/'runs',backend='sim',duration_s=.65,
                      raw_only=False,acknowledge_wiring=False,quiet=True)
    assert status=='completed'
    return folder

def test_run_data_integrity(completed):
    info=inspect_run(completed)
    assert info['integrity']=='ok'
    assert len(info['channel_samples'])==11
    assert len(info['counter_polls'])==2
    assert all(c['n']>=1 for c in info['counter_polls'])
    for ch in info['channel_samples']:
        assert ch['first_index']==0
        assert ch['last_index']==ch['n']-1
    assert not (completed/'RUNNING').exists()
    assert (completed/'COMPLETED').exists()
    meta=json.loads((completed/'metadata.json').read_text())
    assert all(w['closed'] for w in meta['workers'])
    assert meta['simulated'] is True

def test_csv_export_preserves_raw_and_quality(completed):
    result=export_run(completed,'csv')
    with (result/'samples.csv').open() as f:rows=list(csv.DictReader(f))
    assert rows and all('SIMULATED' in x['quality'] for x in rows)
    assert all(x['raw_value'] for x in rows)
    assert all(x['simulated']=='1' for x in rows)
    with (result/'counter.csv').open() as f:c_rows=list(csv.DictReader(f))
    assert c_rows and set(x['channel'] for x in c_rows)=={'q_water_in_l_min','q_water_out_l_min'}

def test_notes(completed):
    add_note(completed,'Independent RPM calculation recorded separately')
    with sqlite3.connect(completed/'measurements.sqlite') as db:
        assert db.execute("SELECT count(*) FROM events WHERE source='operator_wall_clock'").fetchone()[0]==1

def test_monitor_once(completed,capsys):
    watch(completed,once=True)
    assert 't_air_in_c' in capsys.readouterr().out

def test_export_refuses_running(completed):
    (completed/'RUNNING').touch()
    with pytest.raises(RuntimeError,match='Stop/finalize'):export_run(completed,'csv')

def test_attach_rpm_preserves_separate_source(completed,tmp_path):
    source=tmp_path/'rpm.csv'
    source.write_text('t_rel_s,n_impeller_rpm,method,uncertainty_rpm\n0,36,external calculation,\n10,48,external calculation,0.8\n')
    target=attach_rpm(completed,source,'DAQ anchor used as t=0 in the external record')
    assert (target/'record.csv').read_bytes()==source.read_bytes()
    assert json.loads((target/'provenance.json').read_text())['joined_to_samples'] is False

def test_invalid_rpm_rejected(completed,tmp_path):
    source=tmp_path/'bad.csv'
    source.write_text('t_rel_s,n_impeller_rpm,method,uncertainty_rpm\n0,-1,unknown,\n')
    with pytest.raises(ValueError):attach_rpm(completed,source,'test')

def test_raw_only_run(tmp_path,demo,demo_path):
    demo['sampling']['rtd_hz']=5.
    folder,status=run(demo,demo_path,tmp_path/'runs',backend='sim',duration_s=.4,
                      raw_only=True,acknowledge_wiring=False,quiet=True)
    assert status=='completed'
    with sqlite3.connect(folder/'measurements.sqlite') as db:
        assert db.execute("SELECT count(*) FROM samples WHERE stream='analog' AND value IS NOT NULL").fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM samples WHERE stream='analog' AND raw_value IS NOT NULL").fetchone()[0]>0

def test_sample_index_gaps_rejected(tmp_path,demo):
    store=RunStore(tmp_path,demo,Clock.now(),'sim',False)
    block=AnalogBlock('analog',1,10.,0.,1.,np.ones((7,1)),True)
    with pytest.raises(ValueError,match='gap'):store.write(block)
    store.finalize('failed',[],[])

def test_queue_overflow_not_silent():
    q=queue.Queue(maxsize=1)
    Worker.publish(q,1)
    with pytest.raises(RuntimeError,match='dropping data'):Worker.publish(q,2)

def test_worker_fault_stops_run(tmp_path,demo,demo_path,monkeypatch):
    import tankdaq.runner as rr
    class Broken(Worker):
        def produce(self,*args):raise RuntimeError('INJECTED_DISCONNECT')
    monkeypatch.setattr(rr,'simulation_workers',lambda _: [Broken('analog')])
    folder,status=rr.run(demo,demo_path,tmp_path/'runs',backend='sim',duration_s=2.,
                         raw_only=False,acknowledge_wiring=False,quiet=True)
    assert status=='failed'
    assert any('INJECTED_DISCONNECT' in f['message'] for f in inspect_run(folder)['faults'])

def test_bad_duration_rejected(tmp_path,demo,demo_path):
    with pytest.raises(ValueError):run(demo,demo_path,tmp_path,backend='sim',duration_s=-1,
                                     raw_only=False,acknowledge_wiring=False)

def test_low_disk_refused(tmp_path,demo,demo_path):
    demo['storage']['min_free_mb']=1e20
    with pytest.raises(RuntimeError,match='disk'):run(demo,demo_path,tmp_path,backend='sim',duration_s=1,
                                                    raw_only=False,acknowledge_wiring=False)

def test_optional_parquet_export(completed):
    pq=pytest.importorskip('pyarrow.parquet',reason='Optional PyArrow is not installed in this build environment')
    output=export_run(completed,'parquet')
    tab=pq.read_table(output/'samples.parquet')
    assert tab.num_rows>0 and 'raw_value' in tab.column_names
