# Quality review: pier-height-boundary-nodes

## Scope and result

Approved implementation in `C:/Users/sasai/AppData/Local/Temp/codex-pier-height-verification-20261015`, using `review-brief.md`, `review-scope.json`, `review-approved.patch`, and the approved plan. The conflicting live K parser was excluded from the initial code review. Formula/GUI work from another session was treated as upstream context.

No outstanding Critical, High, or Medium findings. The review identified one Low numerical contract defect and one Medium documentation inconsistency; both are now fixed and independently rechecked in the live source. One optional Low display improvement remains. Final live full-suite execution and production publication remain lead responsibilities.

## Findings

### Q1 — Low: a positive H6 can disappear without the required input-range error

- File: `P7橋脚/pier_design/frame_model.py:113` (reviewed snapshot).
- Reproduction: start with the default otherwise-valid geometry/legacy frame; set `H1=0`, `H2=H3=H4=H5=1`, `H6=1e-100`, and legacy centroid `hG=.5`. In both directions, `build_frame_model()` succeeds and returns `footing_top.y == 1.0 == H5`. Thus the positive H6 contribution disappears in the initial sum.
- Cause: `_add_height(base, height, path)` rejects loss of its second operand only. For `H6 + H5`, a small positive first operand can disappear without triggering that guard.
- Impact: an extreme-input case violates the approved rule that positive heights lost to coordinate precision produce an input-range error. Ordinary samples and existing numeric results are unaffected.
- Fix: retain the approved addition order, but validate both positive contributions of the initial H6/H5 sum and report the H6 input path if H6 vanishes. Add both-direction regression tests.
- Status: **fixed and independently rechecked**. `frame_model.py:114–115` now checks the lost-H6 case immediately after the unchanged initial addition. The old H5-loss guard remains intact. The new permanent both-direction regression at `tests/test_frame_model.py:247` was red before the fix and is green. Owner's focused run: 254 passed in 9.72s (`tmp/pier-height-boundary-nodes/model-h6-precision-green.log`). Reviewer separately confirmed both stage-specific H6 errors and compared all 10 ordinary fixture cases × 2 directions against the pre-fix C builder: all 20 complete frames remained exactly equal. Reviewed live source SHA256: `5d4fd8e65ab49b0b941d9e88ce31f8c326b065341b479a7c9762d6a4818d171b`; test SHA256: `d2e430b19700a43df8136acc7154e19ba7c86f52de37cb24a00a12ba7c1dac36`.

### Q2 — Medium: README states the opposite B9 contract from the approved parser

- Files: `P7橋脚/README.md:120`, `:156`, `:313` in the reviewed snapshot (the early paragraph covers all automatic fields; later paragraphs explicitly force B9=B7). The live fixture README was also overwritten by the concurrent session.
- Reproduction: pass `tests/fixtures/pier_models/asymmetric-footing.json` to the approved parsers. `parse_input(...).b_parts == (.35, 5.5, .2)` and `parse_reaction_input(...).geometry.b9 == .2`, while the README states that CLI ignores explicit B9 and uses B7.
- Impact: the documented CLI behavior and asymmetric-sample interpretation contradict the user-approved explicit-B9 policy.
- Fix: distinguish GUI automatic B9 from calculation parsing; explicit numeric B9, including zero, wins; missing/null falls back to B7. Explain that GUI save normalizes .2 to .35 for these samples and that the original asymmetric samples should be verified through CLI.
- Status: **fixed and independently rechecked**. Both proposed documents under `tmp/pier-height-boundary-nodes/approved-docs/P7橋脚/` were independently read. The correction resolves all three contradictions, preserves the other session's 15-significant-digit display sentence, and correctly explains the Single centroid and historical adapters. Both live documents now match these checked proposals byte-for-byte. Live README SHA256: `c556c03dcebf0cd07bc16afc274501f0ac7d8c9503f29f4ea67c06d31cfda55b`; fixture README SHA256: `e1fcf66337c7d375cc9df2118e767a512fe354504f7ae1104cd3077f3138f799`.

### Q3 — Low, optional: tiny nonzero elevation differences round to the same table text

- File: `P7橋脚/pier_design/frame_model_report.py:98`.
- Reproduction: `_coordinate(10.0)` and `_coordinate(10.0 + 1e-13)` both return `10.000`.
- Impact: distinct valid nodes remain distinct in JSON, topology, and member references, but a very small nonzero vertical interval is not visible from the three-decimal coordinate text alone. The existing scientific notation branch covers small absolute coordinates, rather than differences at a nonzero elevation.
- Suggested improvement: optionally choose coordinate precision collectively when distinct coordinates would produce the same text, keeping the normal engineering-scale table unchanged.
- Status: independently reproduced; nonblocking display improvement. This is not a model alias or connectivity defect.

## Independently verified behavior

- The complete alias priority `[4,2,1,3,5,6,7,8]` is applied to full coordinate pairs. Roles/source rows, legacy node audit fields, support and load references use the resulting aliases; zero-length members are omitted without renumbering remaining IDs.
- The Decimal center calculation separates mathematically centered decimal input from a real `1e-100` offset in both directions. H1 section orientation/rounding, rigid null references, body material references, and the fixed load-anchor schema match the approved contract.
- Calculator changes isolate the graph from the original cells, transfers, loads, combinations, materials, springs, and aggregate load heights. Historical numeric assertions are retained; typed adapters preserve old formula snapshots while current sample tests use the actual parsers/CLI.
- The reports draw explicit member endpoints, use ID-keyed labels and semantic dimensions, print current graph tables, and advance actual footer numbers through model-table continuation pages.
- Reviewer probes compared 12 existing before/after JSON pairs across three inputs and four stages. They strictly matched non-frame values, retained compatibility fields, and independently checked the parapet's x/y, area, directional inertia, and exact load anchors. The probe also checked decimal centering and `1e-100` eccentricity in both directions: 16 checks passed.
- The parapet 0610 model drawing and 0620 model table were independently viewed at rendered resolution. No clipping, omitted graph elements, or table overlap was observed.
- Existing shared gate evidence reports 2065 passed, zero skips. The reviewer did not repeat the unchanged full suite. `comparison-final-after.json` and its comparison script were inspected; load-page text/vector/pixel equality is recorded there. Ruff is unavailable and coverage was not measured.

## Codex consultation and verification

Read `.agents/skills/codex-system/SKILL.md` and invoked `codex_consult.py` with a single-line English prompt, `--label quality-pier-height-boundary-nodes --sandbox read-only --timeout 600 --cwd C:/Users/sasai/AppData/Local/Temp/codex-pier-height-verification-20261015 --skip-git-repo-check`.

The wrapper returned `ok:false`, `timed_out:true`, `duration_sec:671.573`, with a verified nonempty 2027-character response. This is not a successful consultation gate. Its captured response identified Q1/Q3 and found no other topology/reference/centering/load-isolation defects; both concrete reproductions were then executed and verified independently by this reviewer. No second consultation was needed after the complete findings were recovered.

- Response: `.agents/logs/codex/20261015T060859Z-quality-pier-height-boundary-nodes.md`.
- Stderr: `.agents/logs/codex/20261015T060859Z-quality-pier-height-boundary-nodes.err.log`.
- Timeout caveat: the Windows cmd parent exited at the subprocess timeout while its node/codex descendants briefly retained the capture pipe. The exact child identities were checked before a guarded stop; they exited naturally before the guard ran, so no process was stopped. This affects consultation collection, not product code.

## Integration constraints

The user confirmed the competing session is stopped; the owners reconciled live B9 and documentation. This reviewer rechecked the H6 fix and both live README files as described above. Ownership stability, final live full-suite execution, and production publication remain lead responsibilities. This report does not certify that production outputs have already been published.
