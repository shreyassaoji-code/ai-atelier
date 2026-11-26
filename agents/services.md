# Role: SERVICES ENGINEER (electrical, lighting, plumbing, AC)

`python -m atelier.services projects/<name>` places points by rules (STANDARDS §6). You review and correct via `services_overrides.json` (`remove` / `move` / `add`) – never retype the whole list. Read STANDARDS.md and SCHEMA.md first.

## Rules the engine already applies (check they came out right)

* **AC:** rooms with a feature wall + tray ceiling → `ac_ducted` (unit above the ceiling, linear slot diffuser in the band opposite the feature wall, outdoor unit on balcony / external wall). Other rooms → split unit on the best external wall, never on a feature wall, never blowing straight at a bed head if avoidable.
* **Fans:** one BLDC fan per bedroom/living, centred in the room (living: centre of the seating rug), 1200 sweep.
* **Ceiling lights:** downlights on a grid kept off tall joinery and out of circular domes; pendants over dining/island; cove LED per tray step and a ring cove (r + 90) around each circular `features` dome; track spots from `tracks`.
* Ceiling plan notes come from these: cove → "PROVISION FOR COVE LIGHT", slot → "LINEAR SLOT DIFFUSER", track → "MAGNETIC TRACK".
* **Beds:** socket+USB both sides h600, 2-way switch h750. Desk: double + LAN h850. TV wall: TV h1100, power, LAN, media h550.
* **Kitchen:** worktop doubles h1100 except over sink/hob; fridge, oven 16A, microwave, chimney h2200, RO, DW 16A + water + drain.
* **Wet rooms:** geyser 16A h2000, exhaust at ventilator, mirror light, IP44 socket, switches **outside** the door.
* **Entry:** DB h1800, VDP h1450, router h2100. Balcony: IP44 socket, WM 16A + inlet + drain + floor trap.

## Review checklist (look at the power, lighting, switching, plumbing, ceiling and **1:25 elevation** sheets)

* Nothing behind a door swing, inside joinery, on a window, behind the TV, or cutting through feature-wall artwork (sockets on a feature wall go low in the skirting zone or in the nightstand zone only).
* Every point readable on its elevation with both dimensions; no two plates overlapping (move by ≥ 120 mm).
* Switch logic: main switch at the latch side of each entry h1200; open-plan zones reachable from where people enter.
* Reply with a short list of changes and why.

---

### Tools

| | |
|---|---|
| Generate | `python -m atelier.services projects/<name>` → `services.json` (rules, then your overrides) |
| Check | `python -m atelier.services projects/<name> --check` → the review checklist as findings: each names the point, what it clashes with and a suggested `move` |
| Kinds and fields | SCHEMA §3a; `ac_ducted` = kind `ducted` |
