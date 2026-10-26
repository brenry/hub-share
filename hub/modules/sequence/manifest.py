"""Edit Video: the tab, its routes, the join job kind (one task that loads no model), and four tools; no screen
settings, no sockets, no card."""
from __future__ import annotations

from hub.core.api import Module, Tab

from . import join, last, routes, tools

MODULE = Module(
    id="sequence",
    title="Edit Video",
    tab=Tab(label="Edit Video", order=20),
    lanes=("changed",),
    jobs={"join": join.plan},
    listings=tools.LISTINGS,
    actions=tools.ACTIONS,
    listens={"job.finished": last.on_finished, "session.ended": last.on_ended, routes.DELETED: routes.on_deleted,
             routes.WRITTEN: routes.on_written},
    routes=routes.ROUTES,
)
