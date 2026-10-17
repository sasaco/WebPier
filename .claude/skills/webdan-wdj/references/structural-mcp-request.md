# structural-mcp feature request for WDJ authoring

Capability snapshot observed on 2026-09-30: `get_capabilities` reported Capacita unavailable. This is historical evidence only and must not be used for an operational decision. Every calculation or engine-validation run must call `get_capabilities` again and prefer that current result. At the observation time, the exposed `webdan_calculate` accepted an existing `.wdj` and returned PDF or Markdown, but no tool created, inspected, or validated a WDJ independently of calculation.

## P0: semantic WDJ composer

Add `webdan_compose_wdj`.

Suggested input:

```json
{
  "baseInputPath": "optional existing .wdj",
  "templateId": "optional versioned canonical template",
  "operations": [
    {"op": "set_rectangular_section", "memberNo": 1, "bMm": 350, "hMm": 350},
    {"op": "set_longitudinal_rebar", "pointIndex": 1, "side": "upper", "diameterMm": 19, "count": 2, "coverToCenterMm": 60, "spacingMm": 230},
    {"op": "set_rebar_grade", "groupNo": 1, "role": "longitudinal", "grade": "SD345"}
  ],
  "dryRun": false,
  "validateWithEngine": true
}
```

Required behavior:

- Require exactly one of base document or a versioned template.
- Preserve unknown fields and producer `ver`.
- Resolve members/points by explicit selectors and reject ambiguous selectors.
- Synchronize denormalized display values (`bar.b/h`, fatigue `b/h`, repeated names).
- Return a normalized summary, semantic diff, warnings/errors with JSON pointers and Japanese UI labels.
- Store the generated WDJ as a job artifact with bytes and SHA-256; never write arbitrary caller paths.
- Optionally run Capacita validation/calculation in the same isolated job.

## P0: inspect and validate without calculating

Add `webdan_inspect_wdj` or `webdan_validate_wdj`.

It should report:

- parser/version/mode and selected application/standard;
- members, groups, points, checks, rebar, material, concrete, force coverage, and calculation selection;
- duplicate IDs, dangling references, unsupported diameters, insufficient bar counts, missing required forces, inconsistent repeated dimensions/names;
- separate `syntaxStatus`, `semanticStatus`, and optional `engineStatus`.

This allows an agent to diagnose an input without producing a report and avoids using the calculation failure text as a schema validator.

## P1: template discovery and capability metadata

- Expose `webdan_list_templates` or advertise template IDs and WDJ producer versions in `get_capabilities`.
- State supported shapes, modes, specifications, reinforcement input modes, and operation types.
- Return a compact input schema/example per template instead of forcing the client to copy large fixture JSON.

## P1: actionable diagnostics

All WDJ-related errors should include:

- stable code;
- severity;
- JSON pointer;
- member/point/group selector;
- WebDan UI label;
- expected and actual value;
- whether the failure is parser, semantic validation, runner execution, or engineering calculation.

## Acceptance scenario

Starting from a canonical H16/manual/rectangle template, compose a document for one 350 x 350 mm member with upper and lower D19-2 (SD345), explicit cover/spacing, Fc24 concrete, and explicit Md/Nd. Inspect it, calculate it, and retrieve the WDJ plus Markdown/PDF artifacts. The returned summary must match every requested engineering input and show no dangling or inconsistent mirrored fields.
