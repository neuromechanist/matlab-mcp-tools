"""Pytest configuration and fixtures for MATLAB MCP Tools tests."""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(scope="session")
def eeglab_path():
    """Path to EEGLAB installation."""
    path = Path(__file__).parent.parent.parent / "eeglab"
    if not path.exists():
        pytest.skip("EEGLAB not found at ../eeglab")
    return path


@pytest.fixture(scope="session")
def sample_data_path(eeglab_path):
    """Path to EEGLAB sample data directory."""
    return eeglab_path / "sample_data"


@pytest.fixture(scope="session")
def tutorial_scripts_path(eeglab_path):
    """Path to EEGLAB tutorial scripts directory."""
    return eeglab_path / "tutorial_scripts"


@pytest.fixture(scope="session")
def eeg_data_file(sample_data_path):
    """Path to continuous EEG data file."""
    path = sample_data_path / "eeglab_data.set"
    if not path.exists():
        pytest.skip("eeglab_data.set not found")
    return path


@pytest.fixture(scope="session")
def eeg_epochs_ica_file(sample_data_path):
    """Path to epoched EEG data with ICA."""
    path = sample_data_path / "eeglab_data_epochs_ica.set"
    if not path.exists():
        pytest.skip("eeglab_data_epochs_ica.set not found")
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
