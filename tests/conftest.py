from pathlib import Path
import pytest
from tankdaq.config import load

ROOT=Path(__file__).parents[1]
@pytest.fixture
def demo(): return load(ROOT/'configs'/'demo.yaml')
@pytest.fixture
def rig(): return load(ROOT/'configs'/'rig.yaml')
@pytest.fixture
def demo_path(): return ROOT/'configs'/'demo.yaml'
