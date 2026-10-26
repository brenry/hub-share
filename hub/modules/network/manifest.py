"""Network: the Settings card for this server's addresses (read-only) and paired devices.

Bind and port change only on the server terminal (`hub network set|reset`). Deleting this
folder removes the card and its routes; pairing and the guard stay in core.
"""
from __future__ import annotations

from hub.core.api import Card, Module, Route

from . import routes

MODULE = Module(
    id="network",
    title="Network",
    routes=(Route("GET", "", routes.view),
            Route("PATCH", "/devices/{id}", routes.rename, body_limit=4096),
            Route("DELETE", "/devices/{id}", routes.remove),
            Route("POST", "/pair", routes.pair, body_limit=4096)),
    card=Card(title="Network", order=900, state=routes.card),
)
