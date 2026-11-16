# WEB-01 + SW-01 | Mechanical CAD Studio v0.1

## Product and route map

| Route | Purpose | Execution boundary |
|---|---|---|
| `/` and `/studio` | Unified CAD workbench | Navigation and local UI only |
| `/autocad` | Original AutoCAD DWG annotation interface | Original Flask/Agent endpoints preserved |
| `/api/model/plan` | Deterministic natural language/parameter parsing | No AI API, COM, CAD macro, SLDPRT or disk writing |

The Studio UI offers Overview, AutoCAD, SolidWorks, Task Center and Template Gallery.
The original AutoCAD UI is embedded as a same-origin iframe at `/autocad`, with a standalone link.
This preserves the original page and API rather than claiming a complete front-end migration.
The ModelPlan Task Center is ephemeral to the current browser page session.
AutoCAD task summaries are fetched from the existing local `/api/task_list` endpoint.

**Do not expose this prototype to the public Internet or untrusted LAN.** Existing AutoCAD endpoints require separate authentication / agent authorization design. The file-security review in PR #1 is **separate and not merged**; this feature branch deliberately uses its original `main` baseline. After those independent PRs are approved, any `app.py` merge conflicts need manual review and both workflows rerun against the resulting SHA.

## Supported offline part families

1. `rectangular_plate` = length, width, thickness.
2. `mounting_plate` = rectangle plus four centered through-holes; diameter and X/Y center pitches explicitly specified.
3. `cylinder` = diameter, height.
4. `bushing` = outer diameter, inner diameter, height.

Allowed numerical dimensions: 0.1–2000 mm, finite. Input requires unit-bearing Chinese phrases, e.g. `长120毫米`, `孔径10毫米`, `X方向孔距90毫米`, `宽边方向间隔50毫米`. Centimetres (`cm` or `厘米`) convert to mm. Missing values cause an error; no guesses are made.

Additional geometry rules:
- Mounting-plate holes must not overlap; gap between neighboring holes must exceed 1 mm.
- Hole center to exterior plate edge must leave 1 mm *outside* the hole radius.
- Bushing single-side wall thickness must be at least 1 mm.
- Four-hole mounting plates support **only four holes**, not arbitrary hole patterns or slots.
- Feature definitions are deterministic, derived exclusively from validated whitelisted parameters. Arbitrary JSON operations and user-supplied macros cannot be executed.

## ModelPlan v1 contract

The machine-readable [JSON Schema](../solidworks_engine/modelplan-v1.schema.json) documents the shape, while the runtime `validate_plan` performs stricter semantic checks by reconstructing the plan. The fixed version `schema_version: "1.0"` and `units: "mm"` permit an independent future SolidWorks executor to consume it with strict contract tests. Every plan contains `part_type`, `parameters`, `features`, `bounding_box_mm`. Features use `extrude` and optionally `cut_through` with explicit sketch types and dimensions. Origin lies at the XY sketch center; Z points in extrusion direction.

Example:

```json
{
  "mode": "text",
  "description": "创建一块长120毫米、宽80毫米、厚8毫米的四孔安装板，孔径10毫米，X方向孔距90毫米，Y方向孔距50毫米。"
}
```

POST this JSON to `http://127.0.0.1:5000/api/model/plan`. Success returns:
- `success: true`
- `plan`: versioned deterministic machine-readable ModelPlan
- `validation_report`: geometry constraints and offline verification boundary
- `preview_svg`: valid 2D illustration based on the plan, not CAD screenshot
- `dry_run`: simulated feature sequence, explicitly `native_cad_generated: false`
- `real_solidworks_executed: false`

Alternatively use `{"mode":"parameters","part_type":"bushing","parameters":{"outer_diameter_mm":40,"inner_diameter_mm":20,"height_mm":60}}`. Errors return status 422 with `success:false`, `field` and a Chinese explanation; bad JSON shape is 400. The API is offline and produces no files on server. Download buttons create local browser copies of `model_plan.json`, `geometry_preview.svg` and `validation_report.json`.

## Local reproduction (no SolidWorks)

```sh
python -m pip install "flask>=3.0,<5" "httpx>=0.28,<1" "Pillow>=10,<13" "requests>=2.32,<3"
python -m unittest discover -s tests -p "test_studio_*.py" -v
python app.py
```

Open `http://127.0.0.1:5000/`. Use the SolidWorks module to submit the four-hole example. Inspect 4 hole centers at `(-45,-25)`, `(45,-25)`, `(-45,25)`, `(45,25)` mm; inspect and download three outputs. In the AutoCAD module, the original `/autocad` page must still load.

`.github/workflows/cad-studio.yml` runs Python 3.11 tests and `node --check` for the new JavaScript on Windows and Linux. **Real SolidWorks COM and DWG processing are not CI tested.** Verify completed workflow jobs against the precise PR head SHA before declaring a pass.

## Later stages, separate authorization

- **SW-02:** A Windows-only SolidWorks COM adapter consumes ModelPlan and generates editable `.SLDPRT`, then validates real dimensions and feature tree. Must use explicit mm→m conversion and isolated output copies. Needs a real installed/licensed SolidWorks instance; not provided here.
- **SW-03:** Add more feature types one at a time (L-bracket, flange, array, fillet, chamfer) with schema and regression tests.
- **DWG-01:** DXF/DWG geometric extraction, view matching, ambiguity resolution, mapping into the same ModelPlan, independently validated.

Current results cannot be presented as completed native CAD models. No paid AI, hardware, AutoCAD automation, or user file writes are part of WEB-01/SW-01.

## Review and rollback

All WEB-01/SW-01 modifications belong to the dedicated `feature/cad-studio-web01-sw01` branch and Draft PR. No direct `main` commits, no auto merge, no force push. Close the PR to decline the change. After approval and merge, revert via a new commit instead of rewriting history. Avoid mixing this feature's scope with existing File Safety PR #1.
