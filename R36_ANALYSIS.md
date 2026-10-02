# R36 Raw Text Mutator TDD Analysis

## STEP 1 — Mutator Selection Authority

### Current Architecture

**HOW_CUSTOM_MUTATOR_IS_SELECTED:**
- Hard-coded via environment variable `AFL_PYTHON_MODULE`
- Set in `scripts/run_alfresco_bounded_feedback.py:2531`
- `env.setdefault("AFL_PYTHON_MODULE", "nv_json_mutator")`

**MUTATOR_SELECTION_SOURCE:**
- Environment variable at AFL++ launch time
- No dynamic selection based on scenario/endpoint

**SCENARIO_AVAILABLE_AT_SELECTION_TIME:**
- YES - scenario is written to `task.json` before AFL++ launches
- Available in task payload: `task_payload["scenario"]` (lines 757-762)
- Values: "metadata_update", "content_update", "multipart_upload"

**TARGET_ENDPOINT_AVAILABLE_AT_SELECTION_TIME:**
- YES - `target_endpoint` field in task.json
- Set at line 737-740 based on scenario

**CURRENT_CONTENT_UPDATE_MUTATOR:**
- `nv_json_mutator.py` (incorrectly applied)

**CURRENT_METADATA_UPDATE_MUTATOR:**
- `nv_json_mutator.py` (correctly applied)

**CURRENT_MULTIPART_MUTATOR:**
- `nv_json_mutator.py` with `NV_MULTIPART_MODE=1` (correctly applied)

### Current Selection Mechanism
- **Type:** Environment-based, hard-coded
- **Location:** `scripts/run_alfresco_bounded_feedback.py`
- **Selection logic:** None - always `nv_json_mutator`

## STEP 2 — Defect Reproduction

**Defect confirmed via test_r36_mutator_defect.py:**

```
PRE_REPAIR_MUTATOR_INPUT_IS_FULL_HTTP = YES
PRE_REPAIR_MUTATOR_OUTPUT_IS_FULL_HTTP = YES
PRE_REPAIR_BODY_BEFORE = RAW_TEXT
PRE_REPAIR_BODY_AFTER_CLASS = JSON_WRAPPED
PRE_REPAIR_BODY_AFTER_IS_RAW_TEXT = NO
PRE_REPAIR_BODY_AFTER_IS_JSON_WRAPPED = YES
PRE_REPAIR_CONTENT_TYPE_PRESERVED = YES
```

**Root cause (nv_json_mutator.py:225-230):**
```python
if not body.strip():
    body = "{}"
try:
    obj = json.loads(body)
except:
    obj = {"raw": body[:128]}  # ← DEFECT: wraps raw text in JSON
```

When input is raw text, `json.loads()` fails and fallback creates `{"raw": "..."}`.

## STEP 3 — Minimal Repair Architecture Decision

**MUTATOR_REPAIR_CLASS:**
`DEDICATED_TEXT_MUTATOR_WITH_SCENARIO_ROUTING`

**Rationale:**
1. **Clean separation:** JSON and text mutation logic are fundamentally different
2. **Arm semantics differ:** 
   - JSON: field_value/boundary/structure operate on JSON nodes
   - Text: need character/line/length-based operations
3. **Maintenance:** Isolated text mutator is easier to test and verify
4. **Precedent:** Repository already uses mode-based routing (NV_MULTIPART_MODE)
5. **Minimal change:** Only affects selection, not C-side MAB/reward logic

**Alternative rejected:**
- Scenario-aware extension of existing mutator would require complex branching
- Risk of regression to metadata_update/multipart scenarios
- Harder to verify arm attribution contracts independently

**Implementation plan:**
1. Create `nv_text_mutator.py` - dedicated raw text mutator
2. Add scenario-based routing in `run_alfresco_bounded_feedback.py`
3. Route content_update → nv_text_mutator
4. Route metadata_update → nv_json_mutator (unchanged)
5. Route multipart → nv_json_mutator with NV_MULTIPART_MODE=1 (unchanged)

## STEP 4 — Raw Text Mutation Contract

### Input/Output Contract
- **INPUT:** Full HTTP testcase with `Content-Type: text/plain`
- **OUTPUT:** Full HTTP testcase with mutated raw UTF-8 text body

### Preservation Requirements
- Request line (method, path, HTTP version)
- Host header
- Content-Type: text/plain
- HTTP envelope structure (headers, blank line separator)
- Valid UTF-8 encoding
- Raw text semantic representation

### Prohibited Operations
- JSON serialization of body
- Wrapping in `{"raw": ...}` or any JSON structure
- Changing request method/path
- Modifying authentication headers
- Mutating into non-text representation

## STEP 5 — Mutation Arm Attribution Contract

**CURRENT_ARM_IDS:**
- 0 = field_value
- 1 = boundary  
- 2 = structure

**CURRENT_ARM_MEANINGS (JSON context):**
- field_value: mutate scalar values in JSON
- boundary: test edge cases (empty, large, special values)
- structure: add/remove optional fields

**TEXT_MUTATOR_ARM_MAPPING:**
- ARM 0 (field_value) → character/token substitution, insertions
- ARM 1 (boundary) → length boundaries (empty, very long), special chars
- ARM 2 (structure) → line-level operations (delete line, reorder, duplicate)

**ACTUAL_ARM_CONFIRMATION_MECHANISM:**
- Current: `os.environ["NV_JSON_ARM_USED"] = str(arm)` (lines 216, 233)
- Text mutator must use same mechanism
- C-side reads this to confirm actual arm used vs selected arm
- Environment variable read by fuzzer after mutation completes

**Preservation strategy:**
- Reuse existing three-arm framework
- Same confirmation protocol: set `NV_JSON_ARM_USED` 
- Text-appropriate semantics per arm
- No changes to C-side MAB logic required
