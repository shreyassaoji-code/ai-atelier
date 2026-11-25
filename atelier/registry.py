"""Every sheet the build can make: name -> (function, title, is_plan_scale).

Kept apart from the sheet modules so none of them has to import the others.
"""
from collections import OrderedDict

from atelier import details, sheets, sheets_ceiling, sheets_services

SHEET_DEFS = OrderedDict(sheets.SHEET_DEFS)
for mod in (sheets_services, sheets_ceiling, details):
    SHEET_DEFS.update(mod.SHEET_DEFS)
SHEETS = OrderedDict((k, v[0]) for k, v in SHEET_DEFS.items())
