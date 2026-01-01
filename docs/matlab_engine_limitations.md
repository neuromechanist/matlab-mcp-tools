# MATLAB Python Engine Limitations

This document describes limitations of the MATLAB Engine API for Python that affect this MCP server's implementation. Understanding these helps explain certain design decisions and workarounds.

## Summary of Key Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| Cannot return struct arrays | Can't use `whos` directly | Query variables individually |
| Field names with underscores | MATLAB syntax error | Use `mcp_type` not `_mcp_type` |
| Base workspace isolation | `evalin('base')` doesn't work | Use engine workspace directly |
| Struct-to-dict conversion | Inconsistent across versions | Handle both dict and struct |
| Large data transfer overhead | High token usage | Selective field retrieval |

---

## Detailed Limitations

### 1. Struct Array Return Restriction

**Issue:** The MATLAB Engine cannot return struct arrays to Python; only scalar structs are supported.

```python
# This fails with: "only a scalar struct can be returned from MATLAB"
result = eng.eval("whos", nargout=1)  # whos returns struct array
```

**Impact:** Cannot use `whos` or similar functions that return struct arrays when there are multiple variables.

**Workaround:** Query variables individually using `who` (returns cell array of names) and then get info for each:

```python
var_names = eng.eval("who", nargout=1)  # Returns cell array - OK
for name in var_names:
    var_class = eng.eval(f"class({name})", nargout=1)
    var_size = eng.eval(f"size({name})", nargout=1)
```

**Affected functions:** `list_workspace_variables()`

---

### 2. Field Name Restrictions

**Issue:** MATLAB struct field names cannot start with underscore when using dot notation.

```matlab
% This causes a MATLAB error
summary._mcp_type = 'large_array';  % Error: Invalid character
```

**Impact:** Cannot use Python-style private field naming conventions.

**Workaround:** Use descriptive names without leading underscores:

```matlab
summary.mcp_type = 'large_array';  % OK
summary.var_class = 'double';       % Instead of 'class' (reserved)
summary.var_size = [10, 10];        % Instead of 'size'
```

**Note:** We also avoid `class` and `size` as field names since they conflict with MATLAB built-in functions.

**Affected functions:** All MATLAB helper functions in `~/.mcp/matlab/helpers/`

---

### 3. Base Workspace Isolation

**Issue:** The MATLAB engine's workspace is separate from the "base" workspace. `evalin('base', ...)` does not access the engine's variables.

```python
eng.eval("x = 5;", nargout=0)  # Creates x in engine workspace
result = eng.eval("evalin('base', 'x')", nargout=1)  # Fails - x not in base
```

**Impact:** Helper functions using `evalin('base', 'whos')` don't see engine variables.

**Workaround:** Use direct evaluation in the engine workspace:

```python
eng.eval("who", nargout=1)  # Works - uses engine workspace
eng.workspace["x"]           # Direct workspace access
```

**Affected functions:** `list_workspace_variables()`, MATLAB helper `mcp_var_info.m`

---

### 4. Inconsistent Struct-to-Dict Conversion

**Issue:** Depending on MATLAB Engine version, structs may be returned as Python dicts or as MATLAB struct objects with `_fieldnames` attribute.

```python
# Newer versions (R2024b)
result = eng.eval("struct('a', 1, 'b', 2)", nargout=1)
# Returns: {'a': 1.0, 'b': 2.0}  (Python dict)

# Older versions
result = eng.eval("struct('a', 1, 'b', 2)", nargout=1)
# Returns: matlab.object with result._fieldnames = ['a', 'b']
```

**Impact:** Code must handle both return types.

**Workaround:** Check for both types in conversion functions:

```python
def convert_struct(info):
    if isinstance(info, dict):
        # Handle Python dict (newer engines)
        return {k: convert_value(v) for k, v in info.items()}
    elif hasattr(info, "_fieldnames"):
        # Handle MATLAB struct object (older engines)
        return {f: convert_value(getattr(info, f)) for f in info._fieldnames}
```

**Affected functions:** `_convert_struct_info()`, `_convert_matlab_value()`

---

### 5. Large Data Transfer Overhead

**Issue:** Transferring large MATLAB arrays to Python is slow and consumes significant memory/tokens.

```python
# Transferring a 1000x1000 matrix
result = eng.workspace["large_matrix"]
# ~8MB of data, ~47,000 tokens estimated
```

**Impact:** Impractical for large neuroscience datasets (e.g., EEGLAB EEG structures can be 10GB+).

**Workaround:** Implement selective retrieval with size limits:

```python
# Instead of getting full workspace
workspace = await engine.get_workspace()  # Transfers everything

# Use selective retrieval
result = await engine.get_variable(
    "EEG",
    fields=["nbchan", "srate", "pnts"],  # Only scalar fields
    max_elements=100                       # Limit array sizes
)
```

**Affected functions:** All workspace retrieval functions; primary motivation for `get_variable()`, `get_struct_info()`

---

### 6. matlab.double Array Handling

**Issue:** MATLAB arrays are returned as `matlab.double` objects which need conversion.

```python
result = eng.eval("rand(3,3)", nargout=1)
# result is matlab.double, not Python list
# Access data via result._data or list(result)
```

**Workaround:** Convert in Python:

```python
if isinstance(value, matlab.double):
    if len(value.size) == 2 and (value.size[0] == 1 or value.size[1] == 1):
        return list(value._data)  # 1D array
    else:
        return [list(row) for row in value]  # 2D array
```

**Affected functions:** `_convert_matlab_value()`, `get_workspace()`

---

### 7. Cell Array Limitations

**Issue:** MATLAB cell arrays are returned as Python lists, but nested cells can have inconsistent behavior.

```python
result = eng.eval("{'a', 'b', 'c'}", nargout=1)
# Returns: ['a', 'b', 'c']  (OK)

result = eng.eval("{1, {2, 3}, 'text'}", nargout=1)
# Nested cells may not convert correctly
```

**Workaround:** For complex cell arrays, consider using MATLAB-side processing to flatten or simplify before returning.

---

### 8. No Streaming Support

**Issue:** Cannot stream large results incrementally; entire result must be transferred at once.

**Impact:** Memory spikes when transferring large arrays; no progress indication for long operations.

**Future consideration:** Implement chunked retrieval for very large arrays.

---

## Recommendations for Users

1. **Use selective retrieval** (`get_variable` with `fields` parameter) for large structs
2. **Check struct info first** (`get_struct_info`) before retrieving large variables
3. **Set appropriate `max_elements`** limits based on your token budget
4. **Use `depth=0`** to explore struct hierarchy without transferring data

## Version Compatibility

These limitations have been tested with:
- MATLAB R2024b (24.2.0)
- MATLAB Engine for Python
- Python 3.10, 3.11

Behavior may vary with different MATLAB versions.

## References

- [MATLAB Engine API for Python](https://www.mathworks.com/help/matlab/matlab-engine-for-python.html)
- [Unsupported MATLAB Types](https://www.mathworks.com/help/matlab/matlab_external/handle-data-returned-from-matlab-to-python.html)
