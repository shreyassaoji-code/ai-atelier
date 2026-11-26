# TEAM – playbook for the orchestrating Claude

You run the studio. One floor-plan image and a brief go in; the album PDF, its key pages as PNG and the "verify on site" list come out. You start each agent, check each GATE yourself, merge their files, run the engine and report. Agents write JSON only; only `atelier/` draws. Read `agents/STANDARDS.md` and `agents/SCHEMA.md` before you start, and give every agent its role file and these two.

Project folder `projects/<name>/`: `plan.png`, `brief.md`, `refs/*` (client reference images), then the files below.

## (a) Flow

```
 plan.png  brief.md  refs/*
     │
     ▼
 ┌──────────┐
 │1 SURVEYOR│──► survey.json                                      GATE 1
 └──────────┘
     │
     ▼
 ┌──────────┬──────────┬──────────┐
 │2 DESIGNER│2 DESIGNER│2 DESIGNER│  in parallel ──► design_A / _B / _C.json      GATE 2
 │    A     │    B     │    C     │
 └──────────┴──────────┴──────────┘
     │
     ▼
 ┌──────────┬──────────┬──────────┐
 │3 JUDGE 1 │3 JUDGE 2 │3 JUDGE 3 │  in parallel ──► scores_1 / _2 / _3.json      GATE 3
 │  Client  │ Architect│ Developer│
 └──────────┴──────────┴──────────┘
     │  winner = highest summed total; its designer applies the judges' must_fix
     ▼
 ┌─────────────┐
 │4 MERGE  (you)│ design_<W>.json ──► design.json                                  GATE 4
 └─────────────┘
     │
     ▼
 ┌────────────┐
 │5 REFERENCE │ (only if refs/ has images) ──► reference.json ──(you merge)──► design.json   GATE 5
 └────────────┘
     │
     ▼
 ┌──────────┐
 │6 SERVICES│ engine rules ──► services.json ; agent ──► services_overrides.json     GATE 6
 └──────────┘
     │
     ▼
 ┌──────────┐
 │7 3D      │ atelier.render3d ──► out/renders/ax_*.png cam_*.png fw_*.png cameras.json   GATE 7
 └──────────┘
     │
     ├──────────────────────────────┐
     ▼                              ▼
 ┌──────────┐                ┌────────────┐
 │8 ALBUM   │◄── viz.json ───│8b VISUALISER│ (optional, needs network)              GATE 8
 └──────────┘                └────────────┘
     │  out/album.pdf + out/pages/NN.png
     ▼
 ┌─────────────────┐
 │9 CHECKER (FRESH)│ ──► out/check.json                                            GATE 9
 └─────────────────┘
     │  must_fix?  yes ──► send each fix to the stage that owns the file, redo from there
     ▼  no
 ┌──────────┐
 │10 DELIVER│  album.pdf · key page PNGs · verify-on-site list · honest agent count
 └──────────┘
```

## (b) Steps, each with its GATE

Do not start a step until the previous GATE passes. A failed GATE goes back to the agent that owns the file, with the exact errors.

| # | Step | Who | Writes | GATE (you check it yourself) |
|---|---|---|---|---|
| 0 | Intake | you | `projects/<name>/` with `plan.png`, `brief.md`, `refs/` | `plan.png` opens and is a floor plan; the brief is there. Missing plan → stop and ask. Missing refs → go on; feature walls will show "no reference image on file". |
| 1 | Survey | 1 surveyor (`surveyor.md`) | `survey.json` | `python -m atelier.validate projects/<name>` → **0 errors**; `python -m atelier.overlay projects/<name>` → open `out/overlay.png`: red walls sit on the plan's walls; computed areas within 3 % of printed ones; every value not printed on the plan has `flag: true`. You have the surveyor's 5-line summary. |
| 2 | Design ×3 | 3 designers, strategies A, B, C (`designer.md`) | `design_A.json`, `design_B.json`, `design_C.json` | For each X: `python -m atelier.validate projects/<name> --design design_X.json` → **0 errors** (warnings explained); `python -m atelier.preview projects/<name> design_X.json` → open `out/preview_X.png` and `out/preview_X_ceiling.png` yourself. All three exist before judging. |
| 3 | Judge ×3 | 3 judges: 1 Client, 2 Architect, 3 Developer (`judge.md`) | `scores_1.json`, `scores_2.json`, `scores_3.json` | `python -m atelier.scores projects/<name>` → all three files valid; winner W = highest total summed over the three judges (tie: the Architect's winner). W's designer applies every `must_fix` of all three judges to `design_W.json`, then GATE 2 again for W only. |
| 4 | Merge | you | `design.json` = copy of `design_W.json` | `python -m atelier.validate projects/<name>` → 0 errors. Keep the losing designs; do not edit them. |
| 5 | Reference | 1 reference interpreter (`reference.md`), only if `refs/` has images | `reference.json`: `{"wall_features": [...], "feature_materials": [...]}` | You merge both lists into `design.json` (replace entries with the same id, add new ones). Then validate → 0 errors and no `W-FEATURE-HIDDEN` / `E-FEATURE-OPENING`; every image in `refs/` is the `ref` of one feature wall. (This overrides "write to design.json" in `reference.md`: agents edit only their own file.) |
| 6 | Services | engine + 1 services engineer (`services.md`) | engine: `services.json`; agent: `services_overrides.json` | `python -m atelier.services projects/<name>`; agent reviews `out/` previews and writes overrides; `python -m atelier.services projects/<name> --check` → **0 findings**. Flagged defaults stay flagged. |
| 7 | 3D | engine | `out/renders/ax_<room>.png`, `cam_<room>-<n>.png`, `fw_<feature>.png`, `cameras.json` | `python -m atelier.render3d projects/<name>` then `… --features` (white model, Workbench: ≈15 s a frame; the build runs both); every camera move it prints is read; `cameras.json` → every frame `rendered: true`. Open every frame: no glare blobs, no view filled by a near surface, axonometrics show the dark cut tops. |
| 8 | Album | engine | `out/album.pdf`, `out/pages/NN.png`, `out/album.json` | `python -m atelier.build projects/<name>` prints `album ✓ … (N sheets)` with N = every sheet; open the key pages (cover, presentation, each room board, each feature wall, ceiling, power) and look. |
| 8b | Visualise | 1 visualiser (`visualiser.md`), optional | `out/renders/viz_<id>_<n>.png`, `viz.json` | Run only if `ak-data.magnific.com` is reachable. Rebuild (step 8). Pre-check §9 shows no FAIL. If blocked: say so in the report; the Blender views stay. |
| 9 | Check | 1 **fresh** checker (`checker.md`) | `out/check.json` | `python -m atelier.check projects/<name>` writes the draft; the checker completes it; `python -m atelier.check projects/<name> --validate` → 0 errors. Verdict `ready` → deliver. `ready after fixes` / `not ready` → each `must_fix` goes to the owner of its file (table below), redo from that step, then a **new** fresh checker. Stop after 3 rounds and report what is left. |
| 10 | Deliver | you | — | Section (e). |

Who owns which file (the only agent that may edit it):

| File | Owner |
|---|---|
| `survey.json` | surveyor |
| `design_<X>.json` | designer X |
| `scores_<N>.json` | judge N |
| `reference.json` | reference interpreter |
| `services_overrides.json` | services engineer |
| `viz.json`, `viz_*.png` | visualiser |
| `check.json` (non-machine items, verdict) | checker |
| `design.json`, `project.json`, the merges | you |
| `services.json`, `out/*` except the above | the engine (`atelier/`), never by hand |

A fix to `design.json` is made in `design_W.json` by designer W (or `reference.json` by the interpreter) and merged again by you – never typed into `design.json` directly, or the next merge loses it.

## (c) Parallel work

- **Step 2: three designers at once**, one strategy each (A, B, C as in `designer.md`). They share only `survey.json` and the brief; none sees another's file.
- **Step 3: three judges at once**, after all three designs pass GATE 2. Judges are new agents, not the designers; none sees another judge's scores.
- Everything else is sequential: each step reads what the one before wrote (the reference needs the winning layout, services need the walls and features, 3D needs the services, the album needs the 3D, the checker needs the album).
- While a render runs in the background you may review, but do not start the album until GATE 7 passes.

## (d) Ground rules

1. **Never invent precision.** A value not read from the plan, the brief or a reference is a default: write it with `flag: true` (or in the `flag` list of the object). The engine prints it with `*` and lists it under "verify on site". A guess is never written as a measurement, and a flag is never dropped to make a sheet look cleaner.
2. **Agents edit only their own file; you merge.** No agent writes another agent's file, `design.json`, `services.json` or anything in `out/`.
3. **The checker is a FRESH agent.** It has not surveyed, designed, judged or merged anything in this project, and it gets only its role file, STANDARDS, SCHEMA and the project folder, not your conversation. Each check round uses a new one.
4. **Report the agent count honestly.** Count the agents that actually ran, by role, including re-runs (e.g. "9 agents: 1 surveyor, 3 designers, 3 judges, 1 services engineer, 1 checker; no reference images, so no interpreter; visualiser not run: Magnific blocked"). Never claim agents, renders, visualisations, sheets or hours that did not happen; quote the build's own sheet count.
5. **A partial build never replaces the full PDF.** `atelier.build --sheet …` only splices pages into an album with the same page list; any failed page leaves `album.pdf` untouched. Deliver only a PDF from a complete build whose page count matches `album.json`.
6. Fix the DATA or the ENGINE, never an output image. Every sheet keeps "Drafted with AI - not for construction until checked and signed".

## (e) Deliverables

1. **`out/album.pdf`**: the complete A3 album from the last full build, with its sheet count.
2. **Key page PNGs** from `out/pages/`: cover, presentation plan, each room board, each feature-wall sheet, ceiling plan, power plan. Send them as files with their page numbers.
3. **The "verify on site" list**: `verify_on_site` from `out/check.json` (every flagged survey and design value and every assumed service point, plus the checker's own), as plain text in your report. It matches the list on the measured drawing.

Your report, short: the verdict and any must_fix left; the honest agent count (rule 4); what is missing (no plan source, no refs, no visualisations) and why.
