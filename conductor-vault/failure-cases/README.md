# Failure Cases
> One file per confirmed failure pattern. Retrieved by pre-risky-action hook.
> Format: what broke, why, how to avoid, confirmed fix.

---

## How to use this folder

- Each file = one failure category (routing, LOM, plugin, export, etc.)
- Phase D (D4) indexes these into ChromaDB → `failure_cases_index`
- Pre-risky-action hook retrieves relevant failure files before RISKY_WRITE

## Index

| File | Category | Failures logged |
|---|---|---|
| `ableton_lom_failures.md` | Ableton LOM limits | 6 confirmed |
| `routing_failures.md` | Bus routing issues | 2 confirmed |
| `plugin_failures.md` | Plugin-specific quirks | 1 confirmed |

---

_Seed this folder by migrating from ableton.md (TEST-BUILD) known failures._
_Then add new ones as they are encountered during production._
