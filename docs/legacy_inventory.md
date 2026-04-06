# Legacy Module Inventory — P0 Assessment

> **Generated as part of P0: Legacy Absorption, Freeze & Safe Deletion**
> Architecture context: new execution core has been established under
> `src/capabilities/`, `src/execution/`, `src/planning/`, `src/problem_semantic/`.

---

## Classification Key

| Class | Meaning |
|-------|---------|
| **A** | Rule/knowledge value — should be absorbed into new mainline |
| **B** | Sample / test / regression value — must not be lost |
| **C** | Pure topic-wrapper shell — primary deletion candidate |
| **D** | Thin compatibility shim — keep temporarily; mark as legacy |

---

## Module Inventory

### `src/physics/dispatcher.py` — **Class C**

**What it does:** Routes `PSDL.scenario_type → solver` via a plain `if/elif` chain.
This is the classic anti-pattern the new architecture replaces.

**Dependencies:** Used by `main.py` (`dispatch_with_validation`) and indirectly
anchors many legacy tests.

**Disposal:** Freeze. Cannot delete in P0 without rewriting `main.py` and 7+
test files. Marked as legacy entry. The new mainline (`Scheduler` + rules)
replaces this routing semantics entirely. Deletion deferred to P1/P2 once
`main.py` is ported to the new pipeline.

---

### `src/physics/analytic.py` — **Class A (largely absorbed)**

**What it does:** Exact closed-form kinematic solutions for free_fall,
projectile, and 1-D elastic collision.

**Knowledge status:**
- `solve_free_fall` / `solve_projectile` → covered by `ConstantGravityRule` +
  `Scheduler` (Euler integration; approximate but same physics).
- `solve_collision_1d_elastic` → covered by `ImpulsiveCollisionRule` with `e=1`.
- Key distinction: analytic.py gives *exact* closed-form results (no integration
  error), while the new rules use Euler time-stepping. Both approaches are
  correct for physics; the analytic versions serve as perfect golden references.

**Disposal:** Freeze as **legacy analytic reference**. Keep for regression
comparison. Do not delete until the new execution layer has equivalent
verified precision for at least the same scenario classes.

---

### `src/physics/engine.py` — **Class D**

**What it does:** PyBullet physics engine wrapper providing numerical
integration as the fallback solver for unrecognized scenario types.

**Unique content:** `apply_boundary()` (elastic/absorbing/periodic wall logic),
`add_box()` / `add_cylinder()` helpers (reserved for future shape support).

**Knowledge status:** No equivalent in new mainline yet. The new execution
core does not yet have a general numerical fallback.

**Disposal:** Keep as **compatibility shim**. Marked as legacy. Cannot delete
until `Scheduler` provides an equivalent numerical fallback path.

---

### `src/templates/free_fall.py` — **Class C + B**

**What it does:** Builds PSDL documents for the canonical free-fall scenario,
including validation targets and source refs. Serves as a test fixture.

**Knowledge status:** PSDL construction logic; no unique physics knowledge.
The template sets `scenario_type = "free_fall"` routing the old dispatcher.

**Disposal:** Freeze. Has heavy **test fixture value** (used by 8+ test files).
Cannot delete without migrating all test fixtures. Keep until P1 provides
scenario-agnostic PSDL fixture builders for the new architecture.

---

### `src/templates/projectile.py` — **Class C + B**

**What it does:** Builds PSDL documents for horizontal-throw projectile
scenarios. Same pattern as `free_fall.py`.

**Disposal:** Same as `free_fall.py` — freeze, keep for test fixture value.

---

### `src/templates/collision.py` — **Class C + B**

**What it does:** Builds PSDL documents for 1-D two-body collision scenarios.
Also exposes `compute_final_velocities()` — a standalone reference calculator
supporting both elastic and perfectly-inelastic collisions.

**Unique content:** `compute_final_velocities()` handles the **perfectly-inelastic**
case (`vf = (m1*v1 + m2*v2) / (m1+m2)`) which is not yet covered by
`ImpulsiveCollisionRule` (current implementation assumes elastic, `e=1`).
This knowledge is noted in `execution/rules/local/impulsive_collision.py`.

**Disposal:** Freeze. Keep for test fixture value and as reference for the
inelastic collision case.

---

### `src/templates/extractor.py` — **Class C → ABSORBED & DELETED in P0**

**What it does:** Lightweight regex-based parameter extractor for Chinese +
English natural language input. Extracts numeric physics parameters for the
three known scenario types.

**Knowledge status:** Architecturally belongs in `src/problem_semantic/extraction/`
(NL → structured parameters is a problem-semantic concern, not a template
concern). Migrated to `src/problem_semantic/extraction/extractors.py`.

**Disposal:** **Deleted in P0** after migration. `src/llm/translator.py` updated
to import from the new canonical location.

---

### `src/llm/translator.py` — **Class D**

**What it does:** NL → PSDL translation (template-first + LLM fallback) plus
`classify_scenario()` (regex scene classification) and `generate_answer()`
(LLM answer generation).

**Knowledge status:** Contains `classify_scenario()` — a regex-based scene
classifier with meaningful Chinese+English pattern sets. This is a D-class
shim for the old pipeline but has retained knowledge value.

**Disposal:** Freeze as **legacy NL interface**. `classify_scenario()` remains
useful; the overall `text_to_psdl()` function is the legacy pipeline entry.
Updated import after extractor migration.

---

## Test Files: Regression/Reference Value

| Test file | Class | Role |
|-----------|-------|------|
| `tests/test_free_fall.py` | B | 3-tier golden regression: analytic, dispatcher+template, PyBullet |
| `tests/test_collision_template.py` | B | Elastic/inelastic collision golden regression |
| `tests/test_projectile_template.py` | B | Projectile golden regression |
| `tests/test_dispatcher.py` | B | Legacy routing contract tests |
| `tests/test_classifier.py` | B | Scenario classifier contract tests |
| `tests/test_minimum_interface.py` | — | **New architecture** tests (not legacy) |
| `tests/test_pipeline_integration.py` | — | **New + legacy** integration tests |
| `tests/test_legacy_regression.py` | — | **New**: golden scenario regression via new execution core |

---

## P0 Actions Summary

| Action | Module | Status |
|--------|--------|--------|
| **Migrate + delete** | `src/templates/extractor.py` | ✅ Done in P0 |
| **New location** | `src/problem_semantic/extraction/extractors.py` | ✅ Created in P0 |
| **Update import** | `src/llm/translator.py` | ✅ Done in P0 |
| **Freeze comment** | `src/physics/dispatcher.py` | ✅ Done in P0 |
| **Freeze comment** | `src/physics/analytic.py` | ✅ Done in P0 |
| **Freeze comment** | `src/physics/engine.py` | ✅ Done in P0 |
| **Freeze comment** | `src/templates/free_fall.py` | ✅ Done in P0 |
| **Freeze comment** | `src/templates/projectile.py` | ✅ Done in P0 |
| **Freeze comment** | `src/templates/collision.py` | ✅ Done in P0 |
| **Freeze comment** | `src/llm/translator.py` | ✅ Done in P0 |
| **New regression tests** | `tests/test_legacy_regression.py` | ✅ Created in P0 |

---

## P0 Tail Items (deferred to P1/P2)

1. **Port `main.py`** to new architecture pipeline (`extract_problem_semantics →
   build_capability_specs → build_execution_plan → Scheduler.run`), then delete
   `src/physics/dispatcher.py` entry in `main.py`.
2. **Delete `src/physics/dispatcher.py`** once main.py and all dispatcher-dependent
   tests are ported to the new pipeline.
3. **Delete `src/templates/free_fall.py`, `projectile.py`, `collision.py`** once
   their test fixture roles are replaced by new-architecture fixtures.
4. **Delete `src/physics/engine.py`** once `Scheduler` provides an equivalent
   numerical fallback.
5. **Extend `ImpulsiveCollisionRule`** to support perfectly-inelastic collisions
   (`e=0`), absorbing the last unique knowledge from `collision.py`.
