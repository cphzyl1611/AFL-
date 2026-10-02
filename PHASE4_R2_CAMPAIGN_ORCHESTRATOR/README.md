# Phase 4 R2 Campaign Orchestrator

## Purpose

Deterministic execution orchestrator for the Phase 4 R2 formal campaign (Blocks 1-30).

This is **execution tooling only** — it does not alter scientific runtime semantics.

## Authority

Loads all parameters from:
- `PHASE4_FORMAL_EXECUTION_FREEZE_R2/`
- Commitment: `1fdf580ef94cdec868924c4d0f4759b5eecc7421684aeb3528c6ebac2d9f879f`

## Key Features

1. **Pre-launch parameter gate**: Blocks any command with wrong budget/seed/backend before process launch
2. **Explicit CLI arguments**: Never relies on runner defaults
3. **Persistent ledger**: Survives interruption, prevents duplicate runs
4. **Fail-fast**: Stops on first invalid run
5. **R2 semantic artifact gate**: Preserves narrow false-negative acceptance
6. **Block 2 special handling**: Carries forward valid SE, excludes old AE attempt, permits ONE authorized retry

## State Machine

- NOT_STARTED
- PRECHECK
- RUNNING_FIRST_BACKEND
- VALIDATING_FIRST_BACKEND
- RESETTING_TARGET
- RUNNING_SECOND_BACKEND
- VALIDATING_SECOND_BACKEND
- VALIDATING_PAIR
- BLOCK_COMPLETE
- CAMPAIGN_COMPLETE
- BLOCKED

## Persistent State

Located at: `PHASE4_R2_CAMPAIGN_STATE/`

Files:
- `campaign_state.json` - Current state machine position
- `block_ledger.jsonl` - Block-level outcomes
- `run_inventory.jsonl` - Every run invocation
- `excluded_attempts.jsonl` - Failed/invalid runs
- `command_audit.jsonl` - Normalized command parameters

## Files

- `campaign_orchestrator.py` - Main orchestrator
- `test_campaign_orchestrator.py` - Offline TDD suite
- `README.md` - This file
- `FILE_LIST.txt` - Package inventory
- `SHA256SUMS.txt` - Integrity checksums

## Usage

```bash
# Dry-run validation
python3 campaign_orchestrator.py --dry-run

# Execute Block 2 AE retry + Blocks 3-30
python3 campaign_orchestrator.py --execute

# Resume after interruption
python3 campaign_orchestrator.py --resume
```

## Testing

```bash
pytest test_campaign_orchestrator.py -v
```

Required test results: ALL PASS

## Constraints

- No automatic retries
- No seed replacement
- No mid-campaign budget changes
- No silent reruns of completed valid blocks
- Fails closed on any gate failure
