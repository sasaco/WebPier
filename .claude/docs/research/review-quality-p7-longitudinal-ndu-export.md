# Quality review: P7 longitudinal NDU export

Review date: 2026-10-17. Reviewer: quality-reviewer. Status: complete. One High finding was confirmed, fixed by the mapping owner and independently verified resolved. No unresolved actionable finding remains in this review scope. Nested Codex consultation completed and independently assessed.

## Review Scope

Product source was reviewed in `C:/Users/sasai/AppData/Local/Temp/p7-ndu-final-review-20261017`, the frozen feature over git HEAD baseline. The shared K: implementation is under an unrelated reporting migration and is not the reviewed integration target. Principal files: `src/jrsnap_design_conditions.py`, `jrsnap_export.py`, `jrsnap_ndu.py`, `jrsnap_readback.py`, relevant `jrsnap_artifacts.py`, baseline rebar/frame/0610/0710 mappings, and `test_jrsnap_export.py`. The approved plan, field map and soil derivation in the original workspace are authoritative context.

Pre-fix source SHA256: `jrsnap_export.py` = `90d7cbb509e978518140f4f0a4f167e14b104233ee6449f193a7a84cdb60f560`; `jrsnap_design_conditions.py` = `2c12c07068d1e2581ab24c7f9552283205f605b8555a2e04376890f24668e901`; `jrsnap_ndu.py` = `fc7b590b0adf170811494366f7819d29ccb40f19a4f7d956bf6d6101f5e6662e`. Q1 line numbers and reproductions refer to this pre-fix state.

## Findings

### Q1 — High, resolved: automatic reinforcement rows could select the wrong tension reinforcement

- Location in the frozen source: `src/jrsnap_export.py:170` and `:212`; serialized by `src/jrsnap_ndu.py:112` and `:113`.
- `_section()` determines `main_face_layers` from the number of longitudinal basic-input rows, but `section.rebar` contains all physical bars sorted by actual y coordinate. It never establishes that the intended longitudinal bars are exactly the first/last N native rows. A transverse-face row can precede or interleave the intended longitudinal rows while all layout checks pass. `SectJikuNum` then applies the chosen bending/shear tension counts to different rows. Automatic reinforcement ratios and the selected tension-steel centroid can therefore describe a different reinforcement selection.
- This is not the documented exclusion of manually moved bars: both reproductions use complete, valid automatic basic layouts. The current standard P7 11-row/76-bar input is unaffected.
- Root and the mapping owner were notified and accepted the issue for a minimal v1 rejection fix.

Reproduction, from the isolated `.` directory using its test helpers and the existing Python environment (no product file edits):

```python
import sys
from copy import deepcopy
sys.path.insert(0, "tests")
from test_jrsnap_export import example_input, calculation, build
from pier_design.jrsnap_ndu import serialize_ndu

# A: only change the transverse face's count and its x cover.
raw = example_input()
raw["鉄筋"]["柱"]["main_rows"][1].update(center_mm=225, per_face_count=11)
model = build(calculation(raw))
print(serialize_ndu(model).decode("cp932"))
# Accepted: SectJikuNum1=13,1,1,1,1,0
# SectRein1-1=100.0,19,2
# SectRein1-2=108.0,32,29
# The intended longitudinal one-layer face is the second native row.
# Transverse centered pitch gives y=(2700-(11-1)*250)/2=100.

# B: insert a second longitudinal layer behind the first transverse row.
raw = example_input()
second = deepcopy(raw["鉄筋"]["柱"]["main_rows"][0])
second.update(layer=2, cover_mode="指定", center_mm=400, clear_gap_mm=260)
raw["鉄筋"]["柱"]["main_rows"].insert(1, second)
model = build(calculation(raw))
print(serialize_ndu(model).decode("cp932"))
# Accepted: SectJikuNum1=13,2,2,2,2,0
# First three rows: 108/D32/29, 350/D19/2, 400/D32/29.
# Intended longitudinal layers are rows 1 and 3, not rows 1 and 2.
```

Both reproductions completed with exit 0 and returned serialized native bytes on the frozen implementation.

Evidence for native semantics: JRSNAP 5.2-L03 official manual PDF 90 and 530, `old.pages` in `.agents/agents/jrsnap-operator/manual-comparison-data/JRSNAP.json`: DRTU/DRTL are upper/lower bending tension-steel layer counts, DRTUV/DRTLV the shear counts, IKFLG=0 selects the tension-steel centroid. The ordered DR/DiR/HR arrays have no face-direction tag. The installed reader mapping is recorded in `tmp/p7-ndu-implementation/core/decompiled/DataInputTool.mdlSectKyoutuu.decompiled.cs:2027`–`:2034`; NDT transfer of the same four integer fields is in `DataInputTool.mdlDATA_NDT.decompiled.cs:2399`–`:2440`. The source mapping and the format together require the intended selection to be representable by upper/lower N rows; merely preserving total bars is insufficient.

Recommended fix: before serialization, establish that the intended longitudinal physical-bar set is exactly the first and last N native rows (including coordinate, diameter, material and multiplicity). Explicitly reject layouts with outer or interleaved transverse bars that cannot be represented under the current profile. Do not silently increase N, reorder physical y coordinates, or substitute tension areas/centroids. Add rejection tests for both reproductions and retain positive coverage for current P7 plus an ordinary contiguous two-layer layout and automatic-equivalent manual detail.

Resolution: the mapping owner added this representability check using automatic layout `row_indices` to identify intended longitudinal physical bars, preserving shared corner bars once. The selected bars are aggregated with the existing direction-row API and compared with both native end ranges, including coordinates, diameter, material and count. No source geometry or tension count is silently altered. Post-fix isolated `jrsnap_export.py` SHA256 is `3f7830dce0b073d0005235a2be8f70a712991974e0672de9c03782953b4c7bea`.

Independent reviewer verification after that hash was frozen (Python stdin script, isolated `.`, exit 0, 4.76 s): reproduction A and B both raised `InputError` containing `先頭・末尾の主筋段数分の配筋行と線路主筋が一致しません`. A contiguous second longitudinal layer at 200 mm was accepted and serialized to 6349 bytes, with selected centers `[108, 200, 2500, 2592]` and `SectJikuNum1=13,2,2,2,2,0`. The owner separately reported 95 core tests passed, including same-row side-bar contamination rejection and shared-corner acceptance; standard P7 NDU remains 6298 bytes and SHA `02e2475aa4c16be3ffbc2ba94f770adb02e3df5e35bfa1e987e71857ea26ed71`. This reviewer inspected the fix itself and reran the original two negative cases plus the positive two-layer case, without repeating the full suite.

## Verified Mapping

No additional actionable issue was found in the reviewed soil, coordinate, loading or native-record mappings:

- Df uses H6+H5+equal cover and is reconciled with the 0500 surface layer. Normal water is bottom-based; P7 gamma2 uses surface wet18/submerged8 and hw2=2.7, obtaining raw12.25531914893617 and adopted12.3. Support gamma1=10, phi42.2 and short-term Ks/Kv/kv are distinct from surface values. Unsupported soil/water/cover conditions fail explicitly.
- y changes to downward positive about footing_top, member directions are normalized, roles drive load/support/control assignment, and the existing 0.010 m segment is retained. D1 spans the full existing column; EQ2 covers h2/h3/h4/micro with the documented local sign. H1 is an equivalent cap-top action, without duplicate line load. EQL preserves its already-applied kh0.2.
- Section m/mm and Ec conversions, physical center cover, source material checks, uniform hoop mapping, four explicit editable inputs, M-theta/profile settings, translational support plus one FootInfo rotation, and the absence of extra Kr follow the field map.
- CP932 strict/CRLF, positional record blocks, empty Tisou, native unset sentinel, controls, case modes and combination order match the documented observed V52 dialect. The initial-profile constants are explicit rather than runtime reads of a sample NDU.

## Validation Evidence and Limits

- Root isolated `.agents/check.ps1`: overall `pass`, pytest exit 0, `217 passed, 2 skipped, 3804 deselected in 40.88s`, recorded in `tmp/p7-ndu-implementation/root/isolated-focused-gate.json`. Root subsequently reported both isolated Tk skips passed individually in fresh interpreters (2.93/4.45 s). These are distinct replay results, not retroactive changes to the original skip statuses.
- Earlier established-suite run remains overall failure: 4021 passed, 1 GUI failure, 1 Tk skip; root supplied successful fresh-process execution of every affected exact node. The full suite was not repeated by this reviewer.
- The fresh isolated acceptance receipt `tmp/p7-ndu-implementation/root/isolated-acceptance.json` has status `complete`, verified UTC `2026-10-17T04:33:16.219002+00:00`, completed UTC `2026-10-17T04:33:17.396841+00:00`. Candidate NDU SHA256 `02e2475aa4c16be3ffbc2ba94f770adb02e3df5e35bfa1e987e71857ea26ed71`; actual installed V52 read/save, two-save stability, independent 166-record/623-field/8-case checks passed. This validates the standard candidate, not the alternate reinforcement reproductions or structural analysis.
- Formal P7 publication and integration with the concurrent reporting migration remain with root; no solver, NDT generation or GUI inspection is claimed. No test coverage percentage was measured.
- The gate/acceptance figures above precede the Q1 source change. The independent post-fix checks are explicitly listed in Q1's resolution; root remains responsible for final integration and renewed source-bound acceptance/publication evidence.

## Codex Consultations

A read-only nested consultation completed with `.agents/skills/_shared/codex_consult.py`, label `quality-review-p7-ndu`, local frozen cwd, existing native Codex PATH and 600 s timeout. Prompt: `.agents/logs/codex/20261017T043314Z-quality-review-p7-ndu.prompt.md`; final response: `.agents/logs/codex/20261017T043314Z-quality-review-p7-ndu.md`; execution trace: `.agents/logs/codex/20261017T043314Z-quality-review-p7-ndu.err.log`. The final response and trace were read; this review does not rely on the child self-report alone. No CLI upgrade, global setting change, product edit or full-suite rerun was requested.

The child proposed a Medium issue because changing the perpendicular-direction hoop's `start_mm`, material or pitch leaves longitudinal `SectSher1` unchanged. This reviewer independently reproduced all three accepted mutations. The observation is real, but the conclusion is not adopted: the authoritative field map explicitly maps **uniform longitudinal hoops**, with direction-specific effective-leg counts, and no requirement establishes equality of both directions' material/pitch/zone properties. A longitudinal-only exporter need not project perpendicular shear settings into that record. Root confirmed that adding a new cross-direction equality constraint would exceed the agreed scope. No evidence was found that those changes corrupt the selected longitudinal section. This is recorded as a rejected scope-mismatch candidate, not an unresolved product finding. Q1 was independently discovered and reproduced by this reviewer.
