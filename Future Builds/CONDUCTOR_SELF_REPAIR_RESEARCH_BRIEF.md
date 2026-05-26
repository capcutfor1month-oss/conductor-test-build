# Conductor Self-Repair / Reliability Assistant — Future Research Brief

> Status: Future research only. Do not build yet.
> Goal: Explore how real engineering systems safely diagnose and repair themselves without giving an AI uncontrolled root access over the product.

---

## 1. Core Idea

Conductor should eventually have a **Self-Repair / Reliability Assistant**.

But the safe version is not:

```text
Conductor gets root permission and edits itself whenever it sees a bug.
```

The safe version is:

```text
Conductor can diagnose, consult a repair manual, propose a patch, run tests in a sandbox/branch, and ask the user/admin before applying anything.
```

This protects the public product from silent architecture drift, broken safety rules, corrupted memory, or hidden code changes.

---

## 2. Why This Matters

Conductor is not a normal app. It controls or advises inside Ableton, touches user projects, remembers preferences, and may eventually execute real studio actions.

If Conductor can repair itself, the repair system must be safer than the bug it is fixing.

The product goal is:

```text
self-diagnosing + repair proposal + user-approved patch
```

Not:

```text
autonomous self-modifying AI
```

---

## 3. Research Question

How have real engineers solved similar self-repair, auto-remediation, reliability, and safe-agent-editing problems?

Do not research only AI coding agents. Study similar engineering patterns:

- Kubernetes controllers / operators
- Terraform drift detection
- SRE runbooks
- incident response automation
- auto-remediation systems
- feature flags and rollback systems
- safe patch generation
- CI/CD protected branches
- agentic coding systems
- self-healing services
- chaos engineering
- policy-as-code guardrails
- audit logs and change approvals

---

## 4. Reference Systems To Study

### 4.1 Kubernetes Operators / Controllers

Research:

- reconciliation loops
- desired state vs actual state
- controller ownership boundaries
- safe retries
- idempotent repairs
- when controllers should stop and alert humans

Conductor mapping:

```text
Conductor detects system drift or failure
→ compares expected subsystem behavior vs actual logs/tests
→ proposes reconciliation
→ does not silently modify safety-critical code
```

---

### 4.2 Terraform / Infrastructure Drift Detection

Research:

- plan before apply
- drift detection
- refresh state
- human approval before destructive apply
- state ownership

Conductor mapping:

```text
repair diagnosis = plan
actual patch = apply
tests = verify
user approval = required for risky changes
```

---

### 4.3 SRE Runbooks / Incident Response

Research:

- runbook automation
- diagnosis checklists
- severity levels
- escalation rules
- postmortems
- incident timelines

Conductor mapping:

```text
conductor-vault/system/repair_manual.md
= runbook for Conductor’s own brain/modules
```

---

### 4.4 Auto-Remediation Systems

Research:

- what repairs can be automatic
- what repairs need approval
- how to avoid repair loops
- how to record remediation attempts
- rollback from failed repairs

Conductor mapping:

```text
minor non-safety config fix → maybe auto-suggest
safety-critical code fix → proposal only + tests + approval
```

---

### 4.5 CI/CD Protected Branches

Research:

- branch protection
- required tests
- code owners
- pull request review
- rollback tags
- release gates

Conductor mapping:

```text
repair assistant can create branch/diff
but cannot merge into main without approval and tests
```

---

### 4.6 Policy-as-Code / OPA

Research:

- deterministic policy gates
- deny/allow decisions
- machine-readable rules
- non-overrideable safety policies

Conductor mapping:

```text
repair assistant must obey repair policies:
- never silently edit never-do rules
- never disable tests
- never weaken ActionProof/readback safety
```

---

### 4.7 Agentic Coding Tools

Research:

- Claude Code
- Codex
- SWE-agent style repair loops
- Devin-like workflows
- patch proposal + test cycle
- failure modes of autonomous code editing

Conductor mapping:

```text
Conductor can learn from coding-agent workflows,
but should not become an unrestricted coding agent inside itself.
```

---

## 5. Conductor-Specific Questions

1. Should Conductor have a `conductor-vault/system/repair_manual.md`?
2. What modules should the repair manual describe?
3. Which failures can Conductor diagnose safely?
4. Which repairs can be proposed but not applied automatically?
5. Which files must be protected from autonomous edits?
6. Should repair run in a temp branch/sandbox only?
7. What tests are required before applying a repair?
8. What should be logged in the black box/debugger?
9. Should repair suggestions be reviewed by Codex/Gemini before apply?
10. How does the repair assistant avoid hallucinating file ownership?
11. How does it avoid weakening safety to make tests pass?
12. How should failed repairs be rolled back?
13. How should user/admin approval work?
14. What does the UI show when Conductor finds a bug?
15. What is allowed in friend-test builds vs public release?

---

## 6. Proposed Future Architecture

### 6.1 Repair Manual First

Create later:

```text
conductor-vault/system/repair_manual.md
```

It should include:

- system overview
- phase ownership
- file ownership
- module responsibilities
- safety-critical files
- common failure symptoms
- likely causes
- required tests per subsystem
- allowed repair actions
- forbidden repair actions
- approval workflow
- rollback instructions

---

### 6.2 Permission Levels

| Level | Name | Allowed? | Meaning |
|---|---|---|---|
| L0 | Observe | Yes | Read logs/tests/status only |
| L1 | Diagnose | Yes | Identify likely root cause |
| L2 | Suggest Patch | Yes | Create proposed diff, not apply |
| L3 | Sandbox Repair | Maybe | Apply in temp branch/sandbox and run tests |
| L4 | Human-Approved Apply | Future | User/admin approves tested patch |
| L5 | Root Self-Modify | Reject | AI silently edits production code |

---

### 6.3 Safe Repair Flow

```text
Bug detected
→ collect logs/debug bundle
→ consult repair_manual.md
→ identify subsystem
→ create repair proposal
→ apply only in sandbox/branch
→ run required tests
→ show diff + test result to user
→ user/admin approves
→ apply to working branch
→ log repair event
→ allow rollback
```

---

## 7. Files That Should Be Protected

Conductor should never silently edit:

```text
rag/action_proof.py
rag/readback.py
rag/undo_engine.py
rag/never_do_check.py
rag/routed_retriever.py
rag/context_pack_builder.py
rag/token_budget.py
rag/corrective_check.py
tools/conductor_bridge.py write endpoints
conductor-vault/producer/never_do_rules.md
data/schemas/*.schema.json
tests/phase_c_eval_set.py
tests/phase_d_*_eval.py
```

These can be changed only through:

```text
proposal → tests → reviewer audit → user/admin approval
```

---

## 8. Things To Avoid

Reject:

- root permission self-repair
- silent code edits
- disabling tests to pass
- weakening safety gates
- editing never-do rules without explicit user approval
- rewriting architecture during repair
- self-modifying memory schemas
- changing ActionProof semantics to hide failures
- auto-patching public users’ systems without approval

---

## 9. Expected Research Output

When we research this properly, expected output should include:

1. Reference systems studied
2. Patterns worth copying
3. Patterns to avoid
4. Self-repair permission model
5. Repair manual schema
6. Protected-file policy
7. Repair workflow design
8. Debugger/black-box logging requirements
9. UI/UX for repair proposals
10. Test requirements
11. Public-release safety requirements
12. Implementation roadmap
13. Claude/Codex action brief

---

## 10. Future Build Classification

This should not be built during Phase D.

Recommended placement:

```text
Phase I — Debugger / Reliability / Self-Repair Assistant
```

Build order should be:

```text
1. Debugger timeline
2. Debug bundle export
3. Repair manual
4. Diagnosis assistant
5. Patch proposal assistant
6. Sandbox repair runner
7. Human-approved apply flow
```

---

## 11. North Star

Conductor should eventually be able to say:

```text
I found why this failed.
Here is the subsystem involved.
Here is the exact proposed repair.
Here are the tests I ran.
Here is what could go wrong.
Do you want to apply this patch?
```

That is safe self-repair.

Conductor should never silently say:

```text
I fixed myself. Trust me.
```

---

## 12. Status

Current status:

```text
Research brief created.
No code should be built yet.
Deep research required before implementation.
```
