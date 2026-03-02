"""Test workspace retrieval tools with real EEGLAB data.

NO MOCKS - All tests use real MATLAB/EEGLAB data via shared session engine.
"""

import pytest


class TestGetVariable:
    """Test get_variable with EEGLAB continuous dataset."""

    @pytest.mark.asyncio
    async def test_scalar_fields_exact_values(self, fresh_continuous_eeg):
        """Scalar fields should return exact known values for continuous data."""
        result = await fresh_continuous_eeg.get_variable(
            "EEG", fields=["nbchan", "srate", "pnts", "trials"]
        )
        assert result["nbchan"] == 32
        assert result["srate"] == 128
        assert result["pnts"] == 30504
        assert result["trials"] == 1  # continuous = 1 trial

    @pytest.mark.asyncio
    async def test_scalar_fields_exclude_data(self, eeglab_loaded_engine):
        """Requesting scalar fields should not return the huge data array."""
        result = await eeglab_loaded_engine.get_variable(
            "EEG", fields=["nbchan", "srate"]
        )
        assert "data" not in result

    @pytest.mark.asyncio
    async def test_depth_zero_returns_struct_info(self, eeglab_loaded_engine):
        """depth=0 should return per-field metadata, not raw data values."""
        result = await eeglab_loaded_engine.get_variable("EEG", depth=0)
        assert isinstance(result, dict)
        # Should have EEG field names as keys with metadata dicts as values
        assert "nbchan" in result
        assert "data" in result
        # The data field should be metadata (dict with type info), not a raw array
        data_entry = result["data"]
        assert isinstance(data_entry, dict), (
            f"depth=0 should return metadata for data, got {type(data_entry)}"
        )
        assert "bytes" in data_entry or "is_numeric" in data_entry

    @pytest.mark.asyncio
    async def test_nested_struct_chanlocs(self, eeglab_loaded_engine):
        """Accessing EEG.chanlocs should return struct array info."""
        result = await eeglab_loaded_engine.get_variable("EEG.chanlocs", depth=0)
        assert result is not None
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_data_max_elements_limits_transfer(self, eeglab_loaded_engine):
        """EEG.data with max_elements=50 should limit what is transferred."""
        result = await eeglab_loaded_engine.get_variable("EEG.data", max_elements=50)
        if isinstance(result, dict) and "_mcp_type" in result:
            assert result["_mcp_type"] in ["large_array", "medium_array"]
            if "sample" in result:
                assert len(result["sample"]) <= 50
        elif isinstance(result, list):
            # Raw list should be limited, not the full 32x30504 array
            assert len(result) <= 50, (
                f"max_elements=50 but got list of {len(result)} elements"
            )
        else:
            # String representation or other format is acceptable
            assert isinstance(result, (dict, str)), (
                f"Unexpected result type: {type(result)}"
            )

    @pytest.mark.asyncio
    async def test_nonexistent_variable(self, eeglab_loaded_engine):
        """Requesting a variable that does not exist should return error."""
        result = await eeglab_loaded_engine.get_variable("totally_nonexistent_xyz")
        assert "_mcp_error" in result

    @pytest.mark.asyncio
    async def test_token_savings(self, eeglab_loaded_engine):
        """Selective retrieval should use far fewer tokens than full workspace."""
        import json

        def estimate_tokens(data):
            return len(json.dumps(data, default=str)) // 4

        full = await eeglab_loaded_engine.get_workspace()
        selective = await eeglab_loaded_engine.get_variable(
            "EEG", fields=["nbchan", "srate", "pnts", "xmin", "xmax"]
        )
        assert estimate_tokens(selective) < estimate_tokens(full)


class TestGetStructInfo:
    """Test get_struct_info with EEGLAB structures."""

    @pytest.mark.asyncio
    async def test_eeg_struct_has_expected_fields(self, eeglab_loaded_engine):
        """EEG struct should contain core fields with type metadata."""
        info = await eeglab_loaded_engine.get_struct_info("EEG")
        for field in ["data", "chanlocs", "event", "nbchan", "srate", "pnts"]:
            assert field in info, f"Missing expected field: {field}"

    @pytest.mark.asyncio
    async def test_eeg_field_class_types(self, eeglab_loaded_engine):
        """Fields should report correct MATLAB class types."""
        info = await eeglab_loaded_engine.get_struct_info("EEG")
        # data should be a numeric (single or double)
        if isinstance(info.get("data"), dict) and "class" in info["data"]:
            assert info["data"]["class"] in ("single", "double")
        # chanlocs should be a struct
        if isinstance(info.get("chanlocs"), dict) and "is_struct" in info["chanlocs"]:
            assert info["chanlocs"]["is_struct"] is True

    @pytest.mark.asyncio
    async def test_chanlocs_fields(self, eeglab_loaded_engine):
        """EEG.chanlocs should have standard channel location fields."""
        info = await eeglab_loaded_engine.get_struct_info("EEG.chanlocs")
        expected = {"labels", "theta", "radius", "X", "Y", "Z"}
        found = set(info.keys())
        # At least most of the expected fields should be present
        overlap = expected & found
        assert len(overlap) >= 4, f"Only found {overlap} of {expected}"

    @pytest.mark.asyncio
    async def test_nonexistent_variable_error(self, eeglab_loaded_engine):
        """get_struct_info on nonexistent variable should return error."""
        info = await eeglab_loaded_engine.get_struct_info("nonexistent_var_xyz")
        assert "_mcp_error" in info


class TestListWorkspaceVariables:
    """Test list_workspace_variables with EEGLAB workspace."""

    @pytest.mark.asyncio
    async def test_eeg_listed_as_struct(self, eeglab_loaded_engine):
        """EEG should appear in workspace listing as a struct."""
        variables = await eeglab_loaded_engine.list_workspace_variables()
        names = [v["name"] for v in variables]
        assert "EEG" in names
        eeg_entry = next(v for v in variables if v["name"] == "EEG")
        assert eeg_entry["class"] == "struct"

    @pytest.mark.asyncio
    async def test_variable_entry_structure(self, eeglab_loaded_engine):
        """Each variable entry should have name, class, size, bytes."""
        variables = await eeglab_loaded_engine.list_workspace_variables()
        assert len(variables) > 0
        for var in variables:
            assert "name" in var
            assert "class" in var
            assert "size" in var
            assert "bytes" in var

    @pytest.mark.asyncio
    async def test_filter_by_pattern(self, eeglab_loaded_engine):
        """Pattern filter should match variable names."""
        eeg_vars = await eeglab_loaded_engine.list_workspace_variables(pattern="^EEG")
        names = [v["name"] for v in eeg_vars]
        assert "EEG" in names
        # All returned names should start with EEG
        for name in names:
            assert name.startswith("EEG"), f"{name} does not match ^EEG"

    @pytest.mark.asyncio
    async def test_filter_by_struct_type(self, eeglab_loaded_engine):
        """Type filter for struct should return only structs."""
        struct_vars = await eeglab_loaded_engine.list_workspace_variables(
            var_type="struct"
        )
        for var in struct_vars:
            assert var["is_struct"] is True


class TestGetWorkspace:
    """Test get_workspace with EEGLAB data."""

    @pytest.mark.asyncio
    async def test_workspace_contains_eeg(self, eeglab_loaded_engine):
        """Full workspace should include EEG variable."""
        ws = await eeglab_loaded_engine.get_workspace()
        assert "EEG" in ws

    @pytest.mark.asyncio
    async def test_non_scalar_struct_recovery(self, eeglab_loaded_engine):
        """Non-scalar structs (chanlocs, event) should have metadata, not error strings."""
        ws = await eeglab_loaded_engine.get_workspace()
        eeg = ws.get("EEG", {})
        if isinstance(eeg, dict):
            # If chanlocs is present, it should not be a raw error string
            chanlocs = eeg.get("chanlocs")
            if chanlocs is not None and isinstance(chanlocs, str):
                # Error strings typically start with "Error" or contain traceback
                assert not chanlocs.startswith("Error"), (
                    "chanlocs should have metadata, not error string"
                )
