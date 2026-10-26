"""Casting: the tab after Storyboard, its routes, the orbit job kind and the job's end."""
from __future__ import annotations

from hub.core.api import Module, Route, SocketGroup, Tab

from . import costume, routes, state

MODULE = Module(
    id="casting",
    title="Casting",
    tab=Tab(label="Casting", order=40),
    lanes=("changed",),
    sockets=(SocketGroup("pictures", "Pictures", ("image",), 9),),
    routes=(Route("GET", "/list", routes.get_list),
            Route("GET", "/draft", routes.get_draft),
            Route("POST", "/cast", routes.post_cast, body_limit=65_536),
            Route("POST", "/again", routes.post_again, body_limit=4096),
            Route("POST", "/approve", routes.post_approve, body_limit=4096),
            Route("POST", "/seat", routes.post_seat, body_limit=4096),
            Route("GET", "/orbit", routes.get_orbit),
            Route("GET", "/costume", costume.get_costume),
            Route("POST", "/costume/cast", costume.post_cast, body_limit=65_536),
            Route("POST", "/costume/again", costume.post_again, body_limit=4096),
            Route("POST", "/costume/approve", costume.post_approve, body_limit=4096),
            Route("POST", "/costume/remove", costume.post_remove, body_limit=4096)),
    jobs={routes.KIND: routes.job},
    listens={"job.finished": state.finished},
)
