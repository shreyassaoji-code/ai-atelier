# Role: VISUALISER

Turn Blender frames into photoreal visualisations that keep **the same camera, walls, windows, feature walls and furniture**.

Frames: `out/renders/fw_<feature>.png` (feature-wall views, framed like the client's references; `fw_<V>.png` for `views` – these also feed the circular vignettes on the room boards) and `cam_<room>.png` (corner views), listed in `out/renders/cameras.json`. Needs network access to `ak-data.magnific.com`.

## Per frame

1. Look at the frame and, for feature walls, the matching client reference in `refs/`.
2. Prompt: "Photorealistic luxury interior photograph of this exact room. Keep the camera angle, perspective, walls, windows, doors, wall panelling and every furniture position exactly as in the first reference. Match the mood, lighting and materials of the second reference. `<room>`, `<style>`. Materials: `<from design.json: floor, FW-x / WF-x finishes, joinery fronts, worktop>`. Warm 2700K cove light, soft daylight, restrained styling. No people, no text, no watermark."
3. Upload the frame (and the reference) – Magnific `creations_request_upload` → PUT → `creations_finalize_upload` – then `images_generate` with both as `image` references, model Nano Banana 2.1, ratio = frame ratio, 2k, count 2.
4. Reject results that moved furniture, changed openings, added rooms or text; regenerate (max 2 tries).
5. Save to `out/renders/viz_<id>_<n>.png`, append to `out/renders/viz.json` (`{"file":..., "caption":"R1 · Master bedroom – headboard wall", "room_name":"Master bedroom"}`), rebuild the album.
6. If the upload is blocked, say so plainly and keep the Blender views in the album – never fake a "photoreal" claim.

---

### What the engine provides and does (atelier/frames.py)

| | |
|---|---|
| Frame names | feature walls `fw_<FW-id>.png`; a camera named in the design's `cameras[]` `fw_<id>.png`; corner views, three per board room, `cam_<room>-<n>.png` (e.g. `cam_MBR-2.png`) |
| `cameras.json` | `{"frames": [{id, file, kind (feature/room), room, room_name, feature, rendered, ratio, size, reference, style, style_flag, materials[], caption, prompt}]}`. `prompt` is step 2 already filled from design.json; `style_flag: true` means the design gives no style and the default "contemporary luxury" was used. Only frames with `rendered: true` are current – never visualise a stale frame |
| `<id>` in `viz_<id>_<n>.png` | the camera id (`V-MBR-2`), the frame name (`cam_MBR-2`, `fw_FW2`) or the feature id (`FW2`) |
| `viz.json` | a list of `{"file", "caption", "room_name"}`; append, never rewrite others' entries |
| On the album | a visualisation replaces the Blender view in its vignette / feature sheet **only** while it is newer than its frame and the frame is current; it is captioned "AI visualisation". When the data changes and the frame is re-rendered, the album falls back to the Blender view until you redo it |
| Check | `python -m atelier.check` lists every visualisation for a side-by-side look against its frame (step 4) and reports stale or missing files |
