"""Stage: the tab after Casting, its routes, the pan job kind and the job's end."""
from __future__ import annotations

from hub.core.api import Module, Route, SocketGroup, Tab

from . import drafts, routes

MODULE = Module(
    id="stage",
    title="Stage",
    tab=Tab(label="Stage", order=45),
    lanes=("changed",),
    sockets=(SocketGroup("pictures", "Pictures", ("image",), 9),),
    routes=(Route("GET", "/sets", routes.get_sets),
            Route("GET", "/set", routes.get_set),
            Route("POST", "/build", routes.post_build, body_limit=65_536),
            Route("POST", "/again", routes.post_again, body_limit=4096),
            Route("POST", "/change", routes.post_change, body_limit=4096),
            Route("POST", "/house", routes.post_house, body_limit=4096),
            Route("POST", "/house-change", routes.post_house_change, body_limit=4096),
            Route("POST", "/approve", routes.post_approve, body_limit=4096),
            Route("POST", "/discard", routes.post_discard, body_limit=4096),
            Route("POST", "/audience", routes.post_audience, body_limit=4096),
            Route("POST", "/delete", routes.post_delete, body_limit=4096),
            Route("GET", "/pan", routes.get_pan)),
    jobs={routes.KIND: routes.job},
    listens={"job.finished": drafts.finished},
)
