# AI Atelier – team playbook (for the orchestrating Claude)

One floor-plan image (+ optional client reference images) in → a luxury-studio interior working-design album out: **~55–60 A3 sheets** (room boards, 1:25 elevations, ceiling sections, DT details, joinery boards), Blender 3D, feature-wall views, and (when the image service is reachable) photoreal visualisations.

Agents write **data** (JSON). Python draws everything (`atelier/`), so every sheet, the 3D model and the render cameras come from one source of truth and always agree.

**Every agent reads `agents/STANDARDS.md` (client's standing requirements) and `agents/SCHEMA.md` (data contract) first.**

```
plan.png ──► 1 SURVEYOR ── survey.json ── overlay check ── validate
                 │
             2 BRIEF: ≤2 questions (programme change, style) + collect reference images → refs/
                 │
             3 DESIGNERS ×3 (parallel: A keep walls · B open plan · C storage) ── design_A/B/C.json ── validate
                 │
             4 JUDGES ×3 (parallel: client · architect · developer) ── scores → winner → design.json
                 │
             5 REFERENCE INTERPRETER (only with reference images) ── wall_features + tray ceilings + look-defining furniture
                 │
             6 SERVICES ENGINEER ── rules engine (incl. ducted-AC, fans, tracks) → review → services_overrides.json
                 │
             7 BUILD   python -m atelier.build projects/<p>   (validate → services → 3D axo + rooms → album)
                       python -m atelier.render3d projects/<p> --features   (feature-wall + `views` 3D → board vignettes)
                 │
             8 CHECKER (fresh agent) ── every page PNG vs STANDARDS.md → check.json → fix → rebuild (max 2 loops)
                 │
             9 VISUALISER ── Blender frames + reference mood → image model → renders/viz.json → rebuild
```

## Steps

1. **Set up** `projects/<slug>/`, copy the plan to `plan.png`, client references to `refs/`, fill `project` fields.
2. **Surveyor** (`agents/surveyor.md`). Gate: validate = 0 errors and overlay visibly matches.
3. **Brief**: at most two questions. If unattended, choose defaults and record them in `brief`.
4. **Designers** ×3 in parallel (`agents/designer.md`). Each must validate with 0 errors and include a designed tray ceiling for every habitable room.
5. **Judges** ×3 in parallel (`agents/judge.md`) using `python -m atelier.preview projects/<p> design_<X>.json` images. Winner = highest mean; ties → best function score. Copy to `design.json`, apply the judges' `must_fix` list.
6. **Reference interpreter** (`agents/reference.md`) if the client sent images – one feature wall per image.
7. **Services** (`agents/services.md`).
8. **Build** + `--features` render. Album ≈ 56 sheets for a 2BHK: 4 room boards, ceiling plan + sections, 1:25 elevations, 3 feature walls, DT-01/02, one JN board per joinery item.
9. **Checker** (`agents/checker.md`) – must be a fresh agent. Fix all must-fix items, rebuild.
10. **Visualiser** (`agents/visualiser.md`) – needs network access to `ak-data.magnific.com` (Settings → Capabilities).
11. **Deliver**: album PDF (always a full build – `--only` rewrites the PDF with just those pages), key page PNGs (a room board, a 1:25 elevation, ceiling plan, ceiling sections, a DT sheet, a joinery board), the "verify on site" list, and an honest count of agents actually run.

## Ground rules

* Never invent precision – unknowns get `flag: true` and print with `*`.
* Indian residential defaults unless told otherwise (STANDARDS §6).
* Agents edit only their own files; the orchestrator merges.
* Agent count reported = agents actually spawned (surveyor 1 + designers 3 + judges 3 + reference 1 + services 1 + checker 1 + visualiser 1 = 11, plus re-runs).

---

### How the engine behaves (read with the steps above)

| Step | What the code actually does |
|---|---|
| 2 Gate | `python -m atelier.validate projects/<p>` and `python -m atelier.overlay projects/<p>` → open `out/overlay.png`. |
| 5 Winner | `python -m atelier.scores projects/<p>` checks the three score files and prints the leader: highest total (= highest mean), a tie broken on the summed `function` score. The judges' `must_fix` goes to the winning designer, who edits `design_<W>.json`; the orchestrator then copies it to `design.json` (agents edit only their own files). |
| 6 Reference | The interpreter writes its feature walls in its own file (`reference.json`: `wall_features`, `feature_materials`, ceiling and furniture changes); the orchestrator merges them into `design.json` and re-validates. |
| 7 Build | `atelier.build` already runs both 3D passes (rooms + axonometrics, then `--features`); the separate `--features` command is only needed after changing a feature wall or a `views` entry without a full build. Frames are a white model (Workbench, ~15 s each); read every camera move the renderer prints. |
| 8 Album size | The sheet count follows the data, not a target: every wall face of every room gets a 1:25 elevation (STANDARDS E5.1), so the sample 2BHK is 74 sheets (37 of them elevations). Report the count the build prints. |
| 9 Checker | `python -m atelier.check projects/<p>` drafts `out/check.json` (measured FAILs with the page and the JSON field to fix); the fresh checker completes it, and `--validate` checks the format. Max 2 fix loops, then report what is left. |
| 10 Visualiser | Without network access to the image service, say so and keep the white-model views; the Visualisations sheet says none was produced. |
| 11 Partial builds | The flag is `--sheet <name>` (not `--only`). A partial build **never** rewrites `album.pdf` with fewer pages: it splices its pages into an album made from the same page list, or leaves the PDF untouched (STANDARDS A2.4). Deliver from a full build anyway. |
| 11 Verify on site | `verify_on_site` in `out/check.json`: every flagged survey and design value and every assumed service point – the same list as on the measured drawing. |
