# Quality review: P7 seismic transverse report regeneration

## Scope and outcome

Reviewed the user-approved plan and the 24-file incremental patch at `.agents/logs/review-diff-p7-seismic-transverse-report-regeneration-incremental.patch`, using `tmp/seismic-transverse-implementation/baseline` to distinguish this feature from pre-existing 0710 and concurrent reinforcement changes. The main scope was shared physical geometry extraction, the 0720 calculator/report, CLI dependency wiring, publication registry, editor integration, and their tests. The final follow-up fixes in `seismic_transverse_calculator.py` and its tests were reviewed directly after the patch snapshot.

Three Medium findings were independently reproduced, reported, fixed by the core implementer, and independently verified. No unresolved Medium or higher correctness finding remains in this review. No product source was edited by the reviewer.

## Findings and resolution

### Q1 — Medium, resolved: reversed physical endpoints produced negative EQ2 resultants

Original location: `src/seismic_transverse_calculator.py`, `_validate_geometry` and `_self_inertia`; final orientation guard is at line 357.

Swapping `node_i` and `node_j` on an otherwise canonical H2 or H3 member passed the absolute-length geometry validation. EQ2 then used signed endpoint subtraction: H2 produced length -2.0 m and resultant -1190.7 kN; H3 produced length -0.7000000000000002 m and resultant -312.56050000000005 kN. H3 endpoint intensities also acquired the wrong physical orientation.

The fix requires downward H2/H3/H4 members in the 0720 geometry validator before EQ2 construction. It preserves canonical upward H1 members and the existing H4 insertion check. Independent replay now rejects reversed H2, H3, and H4 with `InputError`. Regression tests cover all three regions.

### Q2 — Medium, resolved: shared adopted weights could disagree between EQ2 and D1

Original location: `src/seismic_transverse_calculator.py`, `_self_inertia`; final consistency checks are at lines 273–290.

Doubling finite `0600.macro_handoff_single.フーチング.N` while retaining the input snapshot and canonical 0620 result changed EQ2 footing force from 1105.65 to 2211.30 kN, while the copied D1 footing weight remained 4167.4501953125 kN. The input identity and finite-value checks did not detect the inconsistent source pair.

The narrow fix compares the already-consumed 0600 footing weight with the canonical D1 footing point and the 0600 pedestal weight with canonical D1 `details.pedestal_N`. It also requires exactly one D1 footing point. Exact equality is appropriate because both sides preserve the same adopted Single value. Independent replay rejects finite conflicts in both components. The change does not claim to rederive or authenticate every upstream value; it enforces consistency of these directly shared quantities.

### Q3 — Medium, resolved: decimal-equivalent upper heights could create a spurious member

Original location: `src/seismic_transverse_calculator.py`, upper-level input construction, and `seismic_frame.py`, exact-coordinate lookup; final arithmetic fix is at calculator lines 377–378.

With geometry H2=0, H3=0, H4=0.011, H5=0.004, H6=0.005 m, the cap is at 0.020 m. B h1=0.1, h2=0.2 and C h1=0.3, h2=0 created two upper nodes connected by a 5.551115123125783e-17 m geometry-only member. The ordinary 10.3 m cap masks this issue because coordinate addition rounds both levels to the same float.

The fix sums each side's input decimal values with `Decimal(str(h1)) + Decimal(str(h2))` before converting to a coordinate float. It introduces no geometric tolerance and leaves shared 0710 geometry unchanged. Independent replay confirms both decimal-equivalent levels now share one node and one 0.3 m upper member. A separate C height of `math.nextafter(0.3, math.inf)` still produces two distinct levels and preserves its positive tiny member, as required by the exact-coordinate contract.

## Other reviewed behavior

- The normalized baseline comparison shows 0710's product change is the geometry extraction and delegation wrapper. Existing calculations, case definitions, rounding, and report rendering are not changed by that extraction or these final fixes.
- 0720 consumes direct 0600 transverse cases 7/8, canonical 0620 fixed actions, and the current input. The train coefficient is applied once; EQ1/EQL H/M remain at cap_top without a second height transfer. The 0.010 m split expands the old H4 reference into both resulting members.
- Train moment rounding, side-specific bearing arms, negative reactions, separate H3 endpoint intensities, and footing-weight-derived displaced-volume force agree with the approved contract. Point and line-force units remain separate.
- The report uses only the result snapshot, checks displayed decimal substitutions, includes every active bearing through its alternative two-column layout, and renders before atomic replacement. The current four-page layout and rendering-failure preservation are covered by the report gate.
- CLI standalone 0720 computes 0500/0600/0620 dependencies and publishes only its pair. The all-stage registry adds 0720 while FrameWeb stages remain 0610/0620. Existing publication and editor validators obtain the additional pair through the registry.

## Verification

- Independent before-fix reproductions executed all three Codex candidates; the original consult's static claims were not accepted on trust.
- Independent after-fix reproduction: exit 0. Evidence: `tmp/seismic-transverse-implementation/quality-review-final-repros.json`.
- Targeted reviewer pytest: `./.venv/Scripts/python.exe -X utf8 -m pytest tests/test_seismic_transverse_calculator.py tests/test_seismic_transverse_report.py -q`, run from `.`: **114 passed in 22.94 s**, exit 0.
- The lead supplied broader regression and 0710 JSON/PDF/pixel equivalence evidence; those results are not described here as independently rerun by this reviewer.
- The shared `uv --locked` gate is known to stop before pytest because of the existing environment/lock mismatch. The approved plan allows the existing P7 virtual environment fallback. The lead also reported an unrelated concurrent reinforcement-reference failure in the broader suite. This review does not claim a fully green repository or completed GUI verification.

## Codex consultation

Read `.agents/logs/codex/20261017T000707Z-quality-p7-0720-core.md` and its corresponding prompt. The lead's required read-only consultation completed with wrapper `ok=true` in 273.66 seconds. Its three static candidates became the independently reproduced findings above. Its suggested coordinate tolerance was not adopted because that would merge genuinely distinct positive levels. The consult's lack of report/CLI/baseline execution was addressed by direct reviewer inspection and targeted local reproduction, rather than a duplicate consultation.
