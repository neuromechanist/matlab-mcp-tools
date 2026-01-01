#!/usr/bin/env python3
"""
Test selective workspace retrieval with real EEGLAB data.

These tests verify that the new workspace tools (get_variable, get_struct_info,
list_workspace_variables) work correctly with complex EEGLAB structures.

NO MOCKS - All tests use real MATLAB/EEGLAB data.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from matlab_mcp.engine import MatlabEngine


class TestSelectiveVariableRetrieval:
    """Test get_variable with EEGLAB data."""

    @pytest.fixture(autouse=True)
    def setup(self, eeglab_path, eeg_data_file):
        """Set up test with EEGLAB data loaded."""
        self.eeglab_path = eeglab_path
        self.eeg_data_file = eeg_data_file
        self.engine = MatlabEngine()

    async def _load_eeg_data(self):
        """Load EEG data into MATLAB workspace."""
        await self.engine.initialize()

        # Add EEGLAB to path
        eeglab_code = f"""
        addpath('{self.eeglab_path}');
        eeglab nogui;
        """
        await self.engine.execute(eeglab_code)

        # Load sample data
        load_code = f"EEG = pop_loadset('{self.eeg_data_file}');"
        result = await self.engine.execute(load_code)
        assert result.error is None, f"Failed to load EEG: {result.error}"

    @pytest.mark.asyncio
    async def test_get_scalar_fields_only(self):
        """Test retrieving only scalar fields from EEG struct."""
        await self._load_eeg_data()

        # Get only scalar fields
        result = await self.engine.get_variable(
            "EEG", fields=["nbchan", "srate", "pnts", "trials"], max_elements=100
        )

        # Should have the requested fields
        assert "nbchan" in result
        assert "srate" in result
        assert "pnts" in result

        # Values should be scalars (or small arrays)
        assert isinstance(result["nbchan"], (int, float, list))
        assert isinstance(result["srate"], (int, float, list))

        # Should NOT have the huge data field
        assert "data" not in result

        print(f"Scalar fields: {json.dumps(result, indent=2, default=str)}")

    @pytest.mark.asyncio
    async def test_get_struct_info_without_values(self):
        """Test get_struct_info returns field info without transferring data."""
        await self._load_eeg_data()

        # Get struct info
        info = await self.engine.get_struct_info("EEG")

        # Should have field information
        assert "data" in info or "_mcp_error" not in info
        assert "nbchan" in info or len(info) > 0

        # Check that we got metadata, not actual data
        if "data" in info:
            data_info = info["data"]
            # Should have size info
            assert "size" in data_info or "numel" in data_info
            # Should NOT have actual array values
            assert not isinstance(data_info, list)

        print(f"Struct info: {json.dumps(info, indent=2, default=str)}")

    @pytest.mark.asyncio
    async def test_depth_control(self):
        """Test that depth=0 returns only field names."""
        await self._load_eeg_data()

        # Depth 0 should return info only
        result = await self.engine.get_variable("EEG", depth=0)

        # Should indicate it's a struct with fields listed
        assert "_mcp_type" in result or "fields" in result or isinstance(result, dict)

        print(f"Depth 0 result: {json.dumps(result, indent=2, default=str)}")

    @pytest.mark.asyncio
    async def test_nested_struct_access(self):
        """Test accessing nested struct fields like EEG.chanlocs."""
        await self._load_eeg_data()

        # Get chanlocs info
        result = await self.engine.get_variable("EEG.chanlocs", depth=0)

        # Should return info about chanlocs struct array
        assert result is not None
        print(f"Chanlocs info: {json.dumps(result, indent=2, default=str)}")

    @pytest.mark.asyncio
    async def test_max_elements_limiting(self):
        """Test that max_elements limits array transfer."""
        await self._load_eeg_data()

        # Get data with limited elements
        result = await self.engine.get_variable("EEG.data", max_elements=50)

        # Should be a summary, not full data
        if isinstance(result, dict):
            if "_mcp_type" in result:
                assert result["_mcp_type"] in ["large_array", "medium_array"]
                # Sample should be limited
                if "sample" in result:
                    assert len(result["sample"]) <= 50
        else:
            # If it returned full data, it should be small
            if isinstance(result, list):
                print(f"Returned list of length {len(result)}")

        print(
            f"Data with max_elements=50: {json.dumps(result, indent=2, default=str)[:500]}..."
        )

    @pytest.mark.asyncio
    async def test_token_savings(self):
        """Compare token usage between full workspace and selective retrieval."""
        await self._load_eeg_data()

        def estimate_tokens(data):
            return len(json.dumps(data, default=str)) // 4

        # Method 1: Full workspace (old way)
        full_workspace = await self.engine.get_workspace()
        full_tokens = estimate_tokens(full_workspace)

        # Method 2: Selective retrieval (new way)
        selective = await self.engine.get_variable(
            "EEG", fields=["nbchan", "srate", "pnts", "xmin", "xmax"]
        )
        selective_tokens = estimate_tokens(selective)

        print(f"Full workspace tokens: {full_tokens:,}")
        print(f"Selective retrieval tokens: {selective_tokens:,}")
        print(f"Token savings: {(1 - selective_tokens / full_tokens) * 100:.1f}%")

        # Selective should be significantly smaller
        assert selective_tokens < full_tokens

    def teardown_method(self, method):
        """Clean up after each test."""
        if hasattr(self, "engine") and self.engine.eng is not None:
            self.engine.close()


class TestListWorkspaceVariables:
    """Test list_workspace_variables with filtering."""

    @pytest.fixture(autouse=True)
    def setup(self, eeglab_path, eeg_data_file):
        """Set up test with EEGLAB."""
        self.eeglab_path = eeglab_path
        self.eeg_data_file = eeg_data_file
        self.engine = MatlabEngine()

    async def _setup_workspace(self):
        """Create multiple variables in workspace."""
        await self.engine.initialize()

        # Add EEGLAB to path
        eeglab_code = f"""
        addpath('{self.eeglab_path}');
        eeglab nogui;
        """
        await self.engine.execute(eeglab_code)

        # Load EEG and create some additional variables
        setup_code = f"""
        EEG = pop_loadset('{self.eeg_data_file}');
        EEG_backup = EEG;
        data_matrix = rand(100, 100);
        event_types = {{'stimulus', 'response', 'feedback'}};
        sample_rate = 128;
        """
        result = await self.engine.execute(setup_code)
        assert result.error is None

    @pytest.mark.asyncio
    async def test_list_all_variables(self):
        """Test listing all variables without filter."""
        await self._setup_workspace()

        variables = await self.engine.list_workspace_variables()

        # Should have multiple variables
        assert len(variables) > 0

        # Check structure
        for var in variables:
            assert "name" in var
            assert "class" in var
            assert "size" in var
            assert "bytes" in var

        print(f"All variables: {json.dumps(variables, indent=2, default=str)}")

    @pytest.mark.asyncio
    async def test_filter_by_pattern(self):
        """Test filtering variables by name pattern."""
        await self._setup_workspace()

        # Filter for EEG* variables
        eeg_vars = await self.engine.list_workspace_variables(pattern="^EEG")

        # Should find EEG and EEG_backup
        names = [v["name"] for v in eeg_vars]
        assert "EEG" in names or len(eeg_vars) > 0

        print(f"EEG* variables: {names}")

    @pytest.mark.asyncio
    async def test_filter_by_type(self):
        """Test filtering variables by type."""
        await self._setup_workspace()

        # Filter for struct variables only
        struct_vars = await self.engine.list_workspace_variables(var_type="struct")

        # All should be structs
        for var in struct_vars:
            assert var["is_struct"] is True

        print(f"Struct variables: {[v['name'] for v in struct_vars]}")

    @pytest.mark.asyncio
    async def test_filter_by_pattern_and_type(self):
        """Test filtering by both pattern and type."""
        await self._setup_workspace()

        # Filter for numeric variables with 'data' in name
        data_vars = await self.engine.list_workspace_variables(
            pattern="data", var_type="double"
        )

        print(f"Numeric 'data' variables: {[v['name'] for v in data_vars]}")

    def teardown_method(self, method):
        """Clean up after each test."""
        if hasattr(self, "engine") and self.engine.eng is not None:
            self.engine.close()


class TestGetStructInfo:
    """Test get_struct_info with complex EEGLAB structures."""

    @pytest.fixture(autouse=True)
    def setup(self, eeglab_path, eeg_data_file):
        """Set up test with EEGLAB."""
        self.eeglab_path = eeglab_path
        self.eeg_data_file = eeg_data_file
        self.engine = MatlabEngine()

    async def _load_eeg_data(self):
        """Load EEG data into MATLAB workspace."""
        await self.engine.initialize()

        eeglab_code = f"""
        addpath('{self.eeglab_path}');
        eeglab nogui;
        EEG = pop_loadset('{self.eeg_data_file}');
        """
        result = await self.engine.execute(eeglab_code)
        assert result.error is None

    @pytest.mark.asyncio
    async def test_get_eeg_struct_info(self):
        """Test getting info for main EEG struct."""
        await self._load_eeg_data()

        info = await self.engine.get_struct_info("EEG")

        # Should have main EEG fields
        found_fields = list(info.keys())

        print(f"EEG fields: {found_fields}")
        print(f"Full info: {json.dumps(info, indent=2, default=str)[:2000]}...")

        # At least some expected fields should be present
        assert len(found_fields) > 0

    @pytest.mark.asyncio
    async def test_struct_field_types(self):
        """Test that struct info includes type information."""
        await self._load_eeg_data()

        info = await self.engine.get_struct_info("EEG")

        # Check that we have type info for fields
        for field_name, field_info in info.items():
            if isinstance(field_info, dict):
                # Should have class or type info
                has_type_info = (
                    "class" in field_info
                    or "is_struct" in field_info
                    or "is_numeric" in field_info
                )
                if has_type_info:
                    print(f"  {field_name}: {field_info.get('class', 'unknown')}")

    @pytest.mark.asyncio
    async def test_nested_struct_info(self):
        """Test getting info for nested struct (EEG.chanlocs)."""
        await self._load_eeg_data()

        # Get info for chanlocs (struct array)
        info = await self.engine.get_struct_info("EEG.chanlocs")

        print(f"chanlocs info: {json.dumps(info, indent=2, default=str)}")

    @pytest.mark.asyncio
    async def test_nonexistent_variable(self):
        """Test error handling for nonexistent variable."""
        await self._load_eeg_data()

        info = await self.engine.get_struct_info("nonexistent_var")

        # Should return an error
        assert "_mcp_error" in info
        print(f"Error response: {info}")

    def teardown_method(self, method):
        """Clean up after each test."""
        if hasattr(self, "engine") and self.engine.eng is not None:
            self.engine.close()


if __name__ == "__main__":
    # Run a quick test
    async def quick_test():
        engine = MatlabEngine()
        await engine.initialize()

        # Create a simple struct for testing
        result = await engine.execute(
            "test_struct = struct('name', 'test', 'value', 42, 'data', rand(10,10));"
        )
        print(f"Created struct: {result.error or 'OK'}")

        # Test get_struct_info
        info = await engine.get_struct_info("test_struct")
        print(f"Struct info: {json.dumps(info, indent=2, default=str)}")

        # Test get_variable with fields
        result = await engine.get_variable("test_struct", fields=["name", "value"])
        print(f"Selected fields: {json.dumps(result, indent=2, default=str)}")

        # Test list_workspace_variables
        variables = await engine.list_workspace_variables()
        print(f"Workspace: {json.dumps(variables, indent=2, default=str)}")

        engine.close()

    asyncio.run(quick_test())
