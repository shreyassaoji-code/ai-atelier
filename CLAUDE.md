# AI Atelier – rules for Claude (read at the start of every session)

- Units: millimetres, integers. Origin bottom-left, x east, y north.
- Agents write JSON only. Only atelier/ draws.
- Anything not read from the plan: flag:true, printed with * and listed under "verify on site".
- Every sheet carries: "Drafted with AI - not for construction until checked and signed".
- After any drawing change: rebuild, open the PNG, look at it, fix what looks wrong.
- Never claim output you did not produce (renders, agent counts, hours).
- Fix the DATA or the ENGINE. Never patch an output image or hard-code a value in a drawing.
- Read agents/STANDARDS.md and agents/SCHEMA.md before any task.
- No hex colour or font name outside atelier/theme.py.
