# Task: Add `auto` credential_mode that defaults to rhumb_managed when available

## Context
In `packages/api/routes/capability_execute.py`, the `CapabilityExecuteRequest` model (line ~204) has:
```python
credential_mode: str = Field("byo", description="Credential mode (byo, rhumb_managed, agent_vault)")
```

This means agents must explicitly specify `credential_mode: "rhumb_managed"` to use Rhumb's managed credentials. Most agents won't know to do this. We want agents to get the best experience by default.

## Requirements

1. **Change the default to `"auto"`**:
   ```python
   credential_mode: str = Field("auto", description="Credential mode (auto, byo, rhumb_managed, agent_vault). 'auto' uses rhumb_managed when available, falls back to byo.")
   ```

2. **Resolve `auto` before the credential_mode branching** in the `execute_capability` handler. After `cap_services = await _get_capability_services(capability_id)` is called (around line ~674), add resolution logic:
   - If `credential_mode == "auto"`:
     - Check if any mapping in `cap_services` has `credential_modes` containing `"rhumb_managed"` (this field is a comma-separated string or array)
     - Also check if there's an active execution config for the capability (use `_resolve_managed_provider_mapping` or a lighter check against the `rhumb_managed_capabilities` table)
     - If yes → set `request.credential_mode = "rhumb_managed"`
     - If no → set `request.credential_mode = "byo"`
   - Log the resolution: `logger.info("credential_mode auto-resolved to %s for capability %s", request.credential_mode, capability_id)`

3. **Also update the estimate endpoint** (`/v1/capabilities/{capability_id}/estimate`, around line ~1287) which has:
   ```python
   credential_mode: str = Query("byo", description="Credential mode"),
   ```
   Change to `"auto"` with same resolution logic.

4. **Update the MCP tool descriptions** if they reference credential_mode defaults in `packages/mcp/src/tools/`.

5. **Tests**: Add test cases in `packages/api/tests/test_credential_modes.py` or `test_capability_execute.py`:
   - `test_auto_resolves_to_managed_when_config_exists` — mock a capability with a managed config, send without credential_mode → should use rhumb_managed
   - `test_auto_resolves_to_byo_when_no_config` — mock a capability without managed config → should use byo
   - `test_explicit_byo_overrides_auto` — explicitly sending `credential_mode: "byo"` still works even when managed config exists

## Key files
- `packages/api/routes/capability_execute.py` — main changes
- `packages/api/tests/test_capability_execute.py` — add tests
- `packages/api/tests/test_credential_modes.py` — add tests
- `packages/mcp/src/tools/` — update descriptions if needed

## Constraints
- Do NOT break existing explicit `byo`, `rhumb_managed`, or `agent_vault` modes
- Do NOT change the kill switch or rate limiting logic
- Keep the auto-resolution fast (no extra DB queries if possible — use the already-fetched `cap_services`)
- All existing tests must still pass
