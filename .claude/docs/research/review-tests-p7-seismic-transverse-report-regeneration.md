# Test review: P7 seismic transverse report regeneration

Date: 2026-10-17. Reviewer: test-reviewer. Final source review includes the three review fixes and their 23 added calculator regression cases.

## Review Scope

- Reviewed the approved plan, the 24 owned changes in `tmp/seismic-transverse-implementation/task-diff-manifest.json`, the task-relative incremental patch, and the preserved baseline. Pre-existing 0710 work and concurrent rebar changes are excluded from this task's findings.
- Read the new calculator, report and CLI tests; their three fixtures; the corresponding implementation; and normalized baseline-relative changes to the existing CLI, GUI, controller and publication tests. Read existing 0710 calculator test contracts and before/after compatibility evidence.
- Coverage: **not measured**. `gather-diff-utf8.json` has `coverage: null`; no percentage or target comparison is inferred. Ruff was unavailable and was not treated as a passing lint check.
- Shared context gaps and the existing lockfile failure are inherited from the lead's documented context-loader/gate run. The approved existing-venv fallback was used by the implementation team. This reviewer did not repeat broad pytest or GUI runs, following the lead's explicit assignment.

## Findings

No unresolved High or Medium test gap after the reviewed fixes. The following reproduced risks are now covered:

1. **[Medium, resolved] Reversed physical member endpoints.** Earlier malformed-geometry tests checked lengths and missing references but did not reverse H2 or H3 endpoints independently. The quality reviewer reproduced negative EQ2 lengths/resultants. `test_reversed_loaded_member_endpoints_reject_negative_eq2_lengths` now independently reverses H2, H3 and H4 and requires explicit rejection. The implementation validates the distributed members' top-to-bottom orientation while retaining canonical upward H1 behavior; existing H1 cases remain intact.
2. **[Medium, resolved] Decimal-equivalent upper levels.** Integer-only equal-height cases missed B `0.1 + 0.2` versus C `0.3 + 0` at a short physical cap height of `0.020 m`. `test_decimal_upper_height_addition_merges_only_equal_levels` now verifies one shared upper node/member for that case. Its paired `nextafter(0.3, +inf)` case requires separate nodes and a genuinely positive edge shorter than `1e-15 m`, so an epsilon that hides real distinctions would fail. The implementation forms the decimal sums before converting to coordinates.
3. **[Low, resolved hardening] Finite upstream weight contradiction.** Nonfinite-value tests did not cover altered but finite 0600 weights with unchanged 0620 D1. `test_finite_0600_weight_conflict_with_unchanged_0620_d1_is_rejected` now checks footing and pedestal independently and verifies 0620 remains unchanged. Sixteen additional cases cover absent, null, boolean and nonfinite fields on both sources. The check uses the existing Single-transfer weights; it does not replace them with a new geometric weight calculation.

These regressions target observable incorrect acceptance or geometry, rather than copying the implementation's algorithm into expected values.

## Coverage and test quality assessment

- **Independent arithmetic and source distinction:** reference and current-input fixtures are separate, with literal source transcription, PDF provenance and a frozen input SHA. The fixture authoring script imports no product calculation functions. Tests preserve the accepted current EQ1 `9090 kN` versus source-PDF `9080 kN`, `27105 kN m`, signed train rows, C-side arms, nine case meanings and the selected coefficient vector.
- **Rounding is discriminating:** the reviewer executed a small arithmetic audit of existing test inputs. The `earthquake_load=12.3456` case produces correct train N `207.10`, while summing displayed row N would give `207.09`. The signed C-arm case produces M `486.14`, while rounding the sum of raw moments would give `486.13`. Existing assertions therefore detect both prohibited rounding substitutions. This was a diagnostic script, not an added pytest run.
- **Input sensitivity and references:** tests cover earthquake train load/span changes, negative and zero rates, unnormalized rates, independent `hs`/upper geometry/EQL height, S2 versus nonseismic snow, nonrectangular foundation weight, separate beam-bottom/column intensities, nonzero H1, equal/distinct/zero upper levels, array reordering, H4 splitting and coordinate loss. They verify mapped point/line references and preserved distributed-force resultants.
- **Source validation and isolation:** tests cover schema/stage/case identity and uniqueness, snapshots/SHA mismatch, malformed/nonfinite quantities, missing loaded-bearing positions, no legacy/0710/support dependency, and detached results. Fresh input or deep-copied upstream fixtures and scoped monkeypatches avoid shared mutation between cases.
- **Report behavior:** tests check all four pages, headings/order, current values, selected cases/directions, forbidden spring/detail labels, actual node scaling, readable font/bounds, distinct/zero upper levels, H1/distinct intensities, all active bearings, and the full 40 train rows across two tracks. Printed arithmetic is independently recalculated with Decimal. Snapshot-only rendering and both overflow and replace-failure atomicity are tested. Visual comparisons were performed and recorded by the report owner/lead; this reviewer did not claim an additional visual pass.
- **CLI and publication:** tests assert one input read, identity of same-run dependencies, one call per required stage, no 0610/0710 execution for standalone 0720, standalone/all result and PDF-text equality, preservation of all unselected reports/post files, 16 published files and 14 manifest entries, missing/modified 0720 detection, and render/JSON/write/backup/publication rollback with and without existing outputs.
- **Existing contracts retained:** normalized diffs show the old 0710 preview, tamper and identity assertions were retained by parameterization, while stage/count expectations were extended. The expanded-bearing existing acceptance test was fixed in the renderer rather than weakened. The 0710 extraction compatibility evidence records identical complete JSON, PDF bytes, page text and pixels for current and nonround-H1 inputs.

## Test Execution Results

Reviewed passing evidence is partitioned; it is **not** a claim of one fresh monolithic run:

| Scope | Passing evidence | Qualification |
| --- | ---: | --- |
| New 0720 calculator | 100 | Core's final focused run: 100 passed, exit 0, 8.10 s; includes 23 review regressions. |
| Existing 0710 calculator | 90 | Passed in the recorded combined calculator run; complete before/after artifact compatibility also passed. |
| New 0720 report | 14 | Report owner's post-layout-fix suite passed; current-input PDF bytes retained. |
| Eleven affected integration modules | 374 distinct | All have passing executions across initial run, additions, fixed-case/module replay and Tk replay; details in integration work log. |
| Relevant distinct total | 578 | Passing executions across the above runs, before the lead's final focused recheck. |

- Reviewer execution: one targeted arithmetic diagnostic script, exit 0; no independent broad pytest or GUI run.
- Coverage: **not measured**.
- The lead's complementary repository run was `3122 passed, 1 failed, 2 skipped`; the failure is in concurrent `column_rebar_reference` input-version work outside this scope. A Tk replay was `1 passed, 1 skipped`. These results and remaining UI work belong to the lead's final verification record; **the full repository gate is not reported as passing here**.
- The shared check stopped before pytest because of the existing locked dependency mismatch. The approved existing-venv fallback results above do not turn that wrapper into a pass.

## Evidence

- `.agents/logs/agent-teams/team-execute-p7-seismic-transverse-report-regeneration/core.md`
- `.agents/logs/agent-teams/team-execute-p7-seismic-transverse-report-regeneration/integration.md`
- `.agents/logs/agent-teams/team-execute-p7-seismic-transverse-report-regeneration/report.md`
- `tmp/seismic-transverse-implementation/integration/pytest-focused.log`, `pytest-additions.log`, `pytest-identity.log`, `pytest-expanded-snow.log`, `pytest-reaction-after-fix.log`, `pytest-gui-skip-replay.log`, `pytest-collection.log`
- `tmp/seismic-transverse-implementation/0710-compatibility.json`, `0710-before/evidence.json`, `0710-after/evidence.json`
- `tmp/seismic-transverse-implementation/gather-diff-utf8.json`, `remaining-gate.json`, `remaining.xml`, `replay-tk-gate.json`, `replay-tk.xml`

## Review conclusion

The new regressions close the identified geometry/validation gaps without weakening existing assertions. No further Medium-or-higher test change is requested. The lead retains ownership of final focused rechecking and formal output validation/publication.
