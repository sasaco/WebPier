# Quality Review: seismic-longitudinal-loads-report

Review date: 2026-10-16. Reviewer: independent quality reviewer.

## Review Scope

- Approved plan, `seismic_longitudinal_calculator.py`, `seismic_longitudinal_report.py`, CLI and GUI integration, and the 0710 registry addition.
- Canonical 0610 and upstream reaction formulas were read to verify signed loads, transfer precision, and the already applied longitudinal train Kh=0.20.
- Independent source fixture, source page 8/page 12 images, published three-page PDF/JSON, root validation record, and representative changed-geometry report images.
- Existing dependency changes and the concurrent FrameWeb refactor are excluded from this review.

## Findings

- [Medium, resolved] `src/seismic_longitudinal_report.py` (original `_line_inertia` expression at line 153) — Formula factors were displayed at a fixed two decimal places for dimensions and one decimal place for unit weights. Changing only `b1=3.113`, `w1=9.377`, and `unit_weight_body=25.237` produced `Hw1 = 3.11 × 9.38 × 25.2 × 1.00 = 736.68 kN/m`; its printed left-hand product rounds to 735.13, a difference of 1.55 kN/m. The JSON calculation was correct. Original reproduction: `tmp/seismic-longitudinal-loads-implementation/quality-review/nonround.pdf`. The corrected formatter starts at the reference precision and adds digits until decimal evaluation of the printed factors reproduces the printed result. Body, footing, and pedestal substitutions use this logic. Precision candidates that cause a Decimal exception are skipped, and exhausted candidates produce the existing explicit layout error.
- No other actionable findings were identified in the reviewed scope.

## Verified Evidence

- Published JSON matches the independent fixture for train B/C values, signed moments, horizontal girder/train values, inertia values, Wp=-1701, Sw2 N=710/M=19.25, all eight case definitions, and the single combination.
- The train coefficient is descriptive metadata after the already calculated case 10 values are copied; no second factor of 0.20 is applied. Fixed/incremental/limited-incremental classifications remain distinct.
- The adapter copies a physical-frame allowlist and does not copy spring or foundation support metadata. Six current physical nodes and five members are retained. The renderer does not call the shared model-conditions routine that prints foundation springs.
- Upstream and input snapshots remain detached. Runtime calculation and rendering do not reopen saved 0610 results or the reference PDFs; reference paths are provenance strings only.
- Body inertia and footing adopted-volume calculations follow the existing calculation's rounding order. Rectangular display factors are used only when geometry agrees with the adopted volume; tapered/rounded cases use weight/unit-weight factors.
- Published PDF SHA-256: `90e53877bc2d3e94b87b09e4abb39ebb8cbbf9bf424bd18987ac1c74b86fe445`. It has three readable pages in the approved order, no foundation springs or fixed-base symbols, and no extra 0.010 m node. Circled M/F annotations identify the superstructure bearings.
- Input SHA-256: `82d5a2769dfb36b069263c7849e30fdd4a5a23b8c69700613603c51ba430628b`, independently matched to the published JSON.
- Visually inspected published pages 1–3, pedestal/distinct-beam pages 1–2, and tapered-footing page 2. No clipping, unreadable text, or overlap was observed in these artifacts.
- The CLI computes shared upstream stages once, publishes only the selected stage's pair on a 0710-only run, and uses the existing staged publication mechanism. GUI report stems derive from the common registry.

## Codex Consultations

Reused the substantive consultation in `.agents/logs/codex/20261016T130618Z-seismic-longitudinal-loads-quality.md` and its `.prompt.md`, which includes the adapter, renderer inertia formatting, and CLI calculation core. It reported no actionable numerical/data-integrity findings within its embedded-code scope. The independent review agrees with its numerical/data-integrity conclusions but additionally reproduces the display-precision issue above. No redundant consultation was launched.

## Correction Verification

- Independently regenerated the minimal nonround input into `quality-review/nonround-fixed.pdf`; the line is now `Hw1 = 3.113 × 9.377 × 25.237 × 1.00 = 736.68 kN/m`. Extracted all three body inertia equations from the PDF and recomputed their displayed factors with Decimal: all agree with the printed results.
- Independently checked all pages' text bounds and the three-page count. Viewed the full nonround page 2 containing nonzero pedestal, distinct upper/lower beam, column, and adopted-volume footing formulas: all are readable without overlap.
- Independently rerendered the current published baseline snapshot into `quality-review/baseline-fixed.pdf`; its SHA-256 is unchanged at `90e53877bc2d3e94b87b09e4abb39ebb8cbbf9bf424bd18987ac1c74b86fe445`.
- Read the added nonround renderer regression, which parses displayed factors and recomputes body, pedestal force/moment, and footing equations using Decimal. Also read the end-to-end small positive footing unit-weight regression and independently executed the formatter's initial-rounded-zero-divisor retry: PASS.
- Final renderer SHA-256 reviewed: `bd7eb7da0d240e33c1694003e51f59f508548209ea7abaa80a8802f7241dc8f7`.
- Implementer final focused report/CLI suite: **35 passed in 37.58 s**, logged at `tmp/seismic-longitudinal-loads-implementation/report/focused-report-cli.txt`. The implementer also reconfirmed baseline byte equality after the Decimal guard.
- **No unresolved quality findings remain.**

## Validation Limits

The root owns the full repository gate, which was still running when this review was completed. This reviewer did not duplicate the full suite or GUI tests. Quality review is complete with the display-precision finding resolved; overall acceptance remains contingent on the root's final gate result. This is a report/calculation consistency review, not certification of a structural solver or member design.

## 2026-10-17 column-base micro-member correction

Root acceptance addendum: the user required the 0.010 m segment previously excluded. Independent reference/review agent rechecked physical pages 1–5, the final calculator/report and related tests, and baseline/H1 variant PNGs; PASS with no important finding. H4 splits 4.890+0.010 m without moving existing nodes or increasing total height. An enlarged detail identifies the new node and element. No constitutive law or support model is introduced. Calculator 88, report 12, CLI 24 tests passed. Formal pages 2/3 are byte-render identical to the prior PDF; published PDF/JSON match the checked candidate. Concurrent user-side column rebar input changes were retained and current input SHA matches output provenance. Evidence: tmp/seismic-micro-member/published-verification.json.
