# Daily Spend schema migration

## Protected keys

- Active state: `daily-spend-state`
- Immutable pre-migration v1 copy: `daily-spend-state-v1-pre-migration`
- State immediately before an import: `daily-spend-state-before-import`
- v2 state immediately before rollback: `daily-spend-state-v2-before-rollback`

The v1 pre-migration key is write-once. Migration must never overwrite an existing value at that key.

## v1 to v2 sequence

1. Read the exact raw string from `daily-spend-state`.
2. Parse and fully validate it as schema v1 without changing storage.
3. If `daily-spend-state-v1-pre-migration` is empty, save the exact raw v1 string there.
4. Re-read the backup and verify that it exactly matches the source string.
5. Convert each valid v1 expense to v2 in memory.
6. Fully validate the complete v2 state.
7. Write v2 to `daily-spend-state` only after steps 1–6 succeed.
8. If any step fails, leave the active v1 value unchanged and block writes.

The canonical migration input is `fixtures/state-v1-valid.json`.

## Rollback

Rollback is an explicit recovery operation, not part of normal startup.

1. Confirm that `daily-spend-state-v1-pre-migration` contains a valid v1 state.
2. Copy the current raw v2 state to `daily-spend-state-v2-before-rollback` without overwriting an existing rollback copy.
3. Restore the exact v1 backup string to `daily-spend-state`.
4. Roll back the deployed application and Service Worker to the last v1 release before reopening it.

The storage module exposes a tested `rollbackToV1Backup()` helper for steps 1–3. If the v1 backup is missing or invalid, rollback must stop without changing the active state.

## Category boundary

Daily Spend owns its category IDs. Bank-statement categories remain separate. Any future integration must use an explicit conversion table outside both category definitions; neither tool imports or reuses the other tool's category constants.
