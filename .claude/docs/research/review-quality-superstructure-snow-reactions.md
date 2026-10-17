# Quality Review: Superstructure Snow Reactions

## Summary

Final reviewer verdict: PASS. Active Critical: 0; High: 0; Medium: 0; Low: 0. One original Medium finding is resolved.

The approved input, aggregation, GUI editing and report expansion are coherent. The originally confirmed finite-value PDF-formatting failure was fixed locally and independently rechecked. The original Codex NEEDS_REVISION and initial reproducer are retained below as review history.

## Review Scope

Reviewed the 22 feature paths in `tmp/snow-reactions/preservation.json` against `.agents/logs/review-snow-feature.patch` and the starting snapshots in `tmp/snow-reactions/baseline`. This excludes concurrent frame, rebar and other unrelated changes in the canonical HEAD diff.

Source focus: `P7橋脚/pier_design/reaction_inputs.py`, `reaction_weights.py`, `reaction_calculator.py`, `editor_model.py`, `editor_gui.py`, `editor_forms.py`, `reaction_report_snow.py`, `reaction_report_pagination.py`, plus their integration with the unchanged report renderer/layout helpers. Also reviewed the feature tests, initial JSON, field-path fixture and README changes. The approved plan is `.agents/docs/plans/superstructure-snow-reactions.md`.

## Findings

### [Medium, resolved] Accepted finite snow values could fail during PDF generation

- File: `P7橋脚/pier_design/reaction_report_snow.py:100`.
- Original code before the fix: `text = format_value(value, style["format"])`.
- Cause: the shared fixed-decimal formatter calls `excel_round` at `P7橋脚/pier_design/reaction_report_layout.py:70`. Its `Decimal.quantize` uses the default 28-digit decimal context at `P7橋脚/pier_design/reaction_math.py:25-26`. These existing calculation helpers handle ordinary engineering magnitudes; snow is newly routed to them directly after finite-only validation and independent aggregation.
- Reproducer: set `上部工反力.起点側.B支点.支承[0].雪荷重_2年確率` to `1e30` in a normal input. `parse_reaction_input` and `calculate_reactions` succeed, with B = `1e30` and AB = `2e30`. `render_reaction_report` then raises `InputError: 0600 ROUND: 入力または丸め結果が数値範囲を超えています`.
- Impact: the 0600/all run fails for a value accepted by the new finite-number contract. Normal supplied engineering values are unaffected. The existing shared formatter limitation becomes newly reachable through otherwise isolated snow inputs.
- Evidence: `tmp/snow-reactions/quality-large-snow-reproducer.py` and `tmp/snow-reactions/quality-large-snow-reproducer.json`. The probe ran against the real working tree and wrote only temporary review artifacts.
- Original recommendation: contain this in the snow display path; preserve normal one-decimal source formatting and shared calculation helpers. Format finite oversized snow values without the default decimal precision limit, and use readable scientific notation when fixed notation cannot fit. Add a rendered-PDF regression covering a finite magnitude above 28 digits and readable extracted values, while retaining ordinary-value, zero, negative A/D, cache and legacy-cell checks.

### Resolution and Independent Re-review

The final fix is confined to `P7橋脚/pier_design/reaction_report_snow.py:102-112` and regression cases in `P7橋脚/tests/test_reaction_report_snow.py:193-262`. Numeric snow formatting now runs within `localcontext`, with precision sufficient for the value's integer digits plus the retained one decimal. The existing formatter remains authoritative for normal values. At the positive or negative finite float limit, Excel's 15-significant-digit normalization can itself cross the float range; the local fallback formats the rounded Decimal directly and avoids a final infinity conversion. The original fixed-decimal display convention is retained; the earlier suggestion of a scientific-notation policy was not needed to remove the failure and was not introduced.

Independent verification after the owner froze the fix:

- Re-ran the original working-tree `1e30` reproducer: parsing, aggregation and PDF rendering now succeed; B remains `1e30`, AB remains `2e30`, and `render_failed` is `false`.
- Preserved the initial review's observed failure separately in `tmp/snow-reactions/quality-large-snow-reproducer-before-fix.json`, because the implementation owner reran and updated the original JSON path. The current successful result is `tmp/snow-reactions/quality-large-snow-reproducer.json`.
- Ran `uv run --project 'P7橋脚' --locked --group dev python -X utf8 -m pytest 'P7橋脚/tests/test_reaction_report_snow.py' -q`: **8 passed in 14.83s**, exit 0. This covers complete PDFs with `1e30` and `sys.float_info.max`, negative direct A/D extremes, explicit-zero ends, normal positive/negative half-away rounding, cache/result immutability and context identity/settings/flags after each snow-cell draw.
- Ran an additional independent 19-value formatter probe, including signed zero, positive/negative half boundaries, 15-digit normalization, tiny finite values, several large magnitudes and both signed finite float limits. Used a non-default outer precision of 23 and ROUND_DOWN. All expected display strings, context object/settings/flags restoration, and cache preservation passed. Script and results: `tmp/snow-reactions/quality-formatter-recheck.py` / `.json`.
- Independently rendered the ordinary snow fixture into `tmp/snow-reactions/quality-normal-after-fix.pdf`. SHA256 remains `595b919c6c0a5c939335a079bbbb2ec77eacc00ad6f951745538f311d6b4d26e`, exactly equal to the PDF recorded before the fix. All normal PDF content and placement are therefore byte-for-byte unchanged.
- Compared all 22 feature files against the first review's checked snapshot: only the snow renderer and its test file changed. SHA256 checks confirm shared `reaction_math.py`, `reaction_report_layout.py`, `reaction_report.py` and the source layout JSON are unchanged.

Final High/Medium remainder: **High 0, Medium 0**. Re-review evidence is collected in `tmp/snow-reactions/quality-recheck-verification.json`.
## Verified Behavior

- `reaction_inputs.py:128-149` adds frozen, backward-compatible snow input defaults; `:328-372` preserves missing/null A/D until same-case fallback and delegates number validation to the existing full-path reader at `:168-185`. Required parent and dead-input validation still runs first.
- `reaction_weights.py:71-102` independently aggregates all ten B/C slots per case, preserves explicit A/D zero and negative values, ignores cached B/C totals and reports non-finite aggregate paths. Independent fixed-vector and tenth-slot expectations are in `tests/test_reaction_weights.py:169-244`.
- `reaction_calculator.py:300-342` emits `snow_loads` separately. Existing train, impact, longitudinal/transverse, cell, public and Single handoff calculations still use the original dead-load data. The calculation-boundary equality test at `tests/test_reaction_calculator.py:141` and downstream tests at `tests/test_longitudinal_calculator.py:75` / `tests/test_transverse_calculator.py:80` compare full existing results after excluding only added typed snow input.
- `editor_model.py:29-40`, `editor_gui.py:661-693` and `editor_forms.py:186-236` provide virtual old-file inputs, explicit row definitions and refreshed B/C totals. The existing flush/save implementation writes only dirty fields and removes computed B/C snapshots. GUI cases at `tests/test_editor_gui.py:815-927` exercise no-op saves, single edits, paste/delete/undo/redo, read-only totals, type preservation and dash rejection at calculation time.
- `reaction_report_snow.py:33-64` creates per-render source copies; `:75-93` translates cell and rule geometry consistently; `:126-165` draws the support table and all four girder blocks from calculated snow results. The original layout cache and addresses are retained. There are four girder blocks, correcting the consult's incidental reference to five.
- `tests/test_reaction_report_snow.py:68-185` checks 18 support and 60 girder values, all 118 legacy numeric cells, rule bounds, 34 pages, repeated-render/cache safety and G10. Provided `tmp/snow-reactions/report/verification.json` records all later 32 pages unchanged.
- Latest preservation evidence reports 342 existing input leaves preserved, 66 null snow inputs, 29 protected files unchanged and 6 production outputs unchanged; the concurrent 0610/0620 PDF updates are recorded separately as preserved external work.

## Codex Consultations

Read `.agents/skills/codex-system/SKILL.md` and invoked the unchanged shared wrapper using native `codex.exe`, `--sandbox read-only`, and the requested high reasoning setting.

1. `.agents/logs/codex/20261015T070859Z-quality-superstructure-snow-reactions.md`: NOT DETERMINED. The restricted CLI token could not read UNC or K:; this was not counted as a completed review.
2. Copied 76 explicitly selected source/baseline/evidence files to a local temporary snapshot, with each file SHA256-checked against its original. Manifest: `tmp/snow-reactions/quality-consult-snapshot.json`. Re-ran with `--skip-git-repo-check`, without changing permissions, git trust, the wrapper, or global configuration.
3. `.agents/logs/codex/20261015T071300Z-quality-superstructure-snow-reactions.md`: NEEDS_REVISION, one Medium finding. Read the entire response and checked its claims against the real sources. Independently reproduced the reported formatting failure in the working tree. No other actionable quality findings were established. That original Medium was subsequently fixed and independently verified as documented above; the original consult file remains unchanged with NEEDS_REVISION. A further CLI consult was not needed for this localized formatter correction, whose code, exact failure, normal rounding, finite limits and PDF preservation were directly checked.

## Verification and Limitations

This reviewer did not rerun the full suite or Tk suite. The post-fix targeted report tests and probes above were run independently. The first direct pytest launcher attempt hit a PyMuPDF DLL import error during collection; rerunning with the project gate form, `python -X utf8 -m pytest`, collected and passed all 8 cases. The pre-fix parent gate evidence is `overall: pass`, `2308 passed, 1 skipped`; the parent separately replayed the previously skipped reaction GUI case successfully (`1 passed`) and reported 167 owned GUI tests with no skips. These are distinct evidence sets, not an altered full-suite count. The lead owns the post-fix full-suite gate; this focused re-review does not substitute for it.

The local consult did not have the global canonical diff or integration-gate JSON, but it had the exact feature diff, source, baseline, feature tests and relevant preservation/pipeline/PDF evidence. This reviewer read the integration gate in the real workspace. Shared rule files referenced by the skill (`.agents/rules/coding-principles.md`, `codex-delegation.md`, `language.md`, `cli-execution.md`) were absent. Fixed source geometry and font/style reuse are intentional plan constraints and were not flagged as arbitrary style issues.

No product or test files were edited by this reviewer. No commits, staging, resets, application output updates, global configuration changes or subagents were performed.

## Final Lead Verification

After the localized formatting correction, the lead's final full gate passed: 2311 passed, 1 skipped in 245.12s (0:04:05). The original one Medium finding is resolved; independent quality re-review has no active High/Medium findings. The normal QA PDF is byte-identical to its pre-fix version, and all later 32 pages match baseline bitmaps. This addendum records coordinated lead evidence rather than a further reviewer-run full suite. See `tmp/snow-reactions/integration.json` and `tmp/snow-reactions/quality-recheck-verification.json`.
