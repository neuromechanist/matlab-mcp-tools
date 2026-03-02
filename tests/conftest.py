"""Pytest configuration and fixtures for MATLAB MCP Tools tests."""

import os
import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _find_eeglab_path():
    """Resolve EEGLAB installation path.

    Check order: EEGLAB_PATH env var, ../eeg/eeglab, ../eeglab (legacy).
    Raises FileNotFoundError if EEGLAB_PATH is set but invalid.
    """
    env_path = os.environ.get("EEGLAB_PATH")
    if env_path:
        p = Path(env_path)
        if not p.exists():
            raise FileNotFoundError(
                f"EEGLAB_PATH set to '{env_path}' but path does not exist"
            )
        return p

    base = Path(__file__).parent.parent.parent
    for candidate in ["eeg/eeglab", "eeglab"]:
        p = base / candidate
        if p.exists():
            return p
    return None


@pytest.fixture(scope="session")
def eeglab_path():
    """Path to EEGLAB installation."""
    path = _find_eeglab_path()
    if path is None:
        pytest.skip("EEGLAB not found")
    return path


@pytest.fixture(scope="session")
def sample_data_path(eeglab_path):
    """Path to EEGLAB sample data directory."""
    path = eeglab_path / "sample_data"
    if not path.exists():
        pytest.skip(f"EEGLAB sample_data not found at {path}")
    return path


@pytest.fixture(scope="session")
def tutorial_scripts_path(eeglab_path):
    """Path to EEGLAB tutorial scripts directory."""
    path = eeglab_path / "tutorial_scripts"
    if not path.exists():
        pytest.skip(f"EEGLAB tutorial_scripts not found at {path}")
    return path


@pytest.fixture(scope="session")
def matlab_engine():
    """Create a shared MATLAB engine for all tests."""
    import asyncio

    from matlab_mcp.engine import MatlabEngine

    engine = MatlabEngine()
    asyncio.get_event_loop().run_until_complete(engine.initialize())
    yield engine
    engine.close()


@pytest.fixture
def async_engine(matlab_engine):
    """Provide the engine for async tests."""
    return matlab_engine


@pytest.fixture(scope="session")
def eeglab_loaded_engine(matlab_engine, eeglab_path, sample_data_path):
    """Shared engine with EEGLAB initialised and continuous dataset loaded.

    Loads eeglab_data.set (32ch, 128Hz continuous) into the EEG variable.
    Session-scoped so EEGLAB init + data load happens only once.

    NOTE: Tests that execute MATLAB code may modify the EEG variable (e.g.,
    epoching, resampling). Tests needing exact continuous-data values should
    use the ``fresh_continuous_eeg`` fixture instead.
    """
    import asyncio

    data_file = sample_data_path / "eeglab_data.set"
    if not data_file.exists():
        pytest.skip("eeglab_data.set not found")

    loop = asyncio.get_event_loop()

    # Add EEGLAB to path and initialise (nogui)
    init_code = f"addpath('{eeglab_path}'); eeglab nogui;"
    result = loop.run_until_complete(matlab_engine.execute(init_code))
    if result.error:
        pytest.skip(f"EEGLAB init failed: {result.error}")

    # Load continuous dataset
    load_code = f"EEG = pop_loadset('{data_file}');"
    result = loop.run_until_complete(matlab_engine.execute(load_code))
    if result.error:
        pytest.skip(f"Failed to load EEG data: {result.error}")

    yield matlab_engine


@pytest.fixture(scope="session")
def eeglab_epochs_engine(eeglab_loaded_engine, sample_data_path):
    """Shared engine with epoched+ICA dataset loaded into EEG_epochs.

    Loads eeglab_data_epochs_ica.set into EEG_epochs variable.
    The continuous EEG variable from eeglab_loaded_engine remains available.
    """
    import asyncio

    epochs_file = sample_data_path / "eeglab_data_epochs_ica.set"
    if not epochs_file.exists():
        pytest.skip("eeglab_data_epochs_ica.set not found")

    loop = asyncio.get_event_loop()
    load_code = f"EEG_epochs = pop_loadset('{epochs_file}');"
    result = loop.run_until_complete(eeglab_loaded_engine.execute(load_code))
    if result.error:
        pytest.skip(f"Failed to load epochs data: {result.error}")

    yield eeglab_loaded_engine


@pytest.fixture
def fresh_continuous_eeg(eeglab_loaded_engine, sample_data_path):
    """Reload continuous EEG dataset to ensure known state.

    Use this fixture for tests that need exact values from the continuous dataset
    and may run after tests that modify the EEG variable.
    """
    import asyncio

    data_file = sample_data_path / "eeglab_data.set"
    load_code = f"EEG = pop_loadset('{data_file}');"
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(
        eeglab_loaded_engine.execute(load_code, capture_plots=False)
    )
    if result.error:
        pytest.skip(f"Failed to reload EEG data: {result.error}")
    return eeglab_loaded_engine
