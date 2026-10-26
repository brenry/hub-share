"""Media: the Temp (the pictures the hub makes and takes in, with their groups), the clips (`/clips`, their own
page), the sounds (`/sounds`, their own page) and the Drive (`paths.drive`).

Core pushes each new `generation` on the core media lane; this module publishes `media.changed` after a change.
"""
from __future__ import annotations

from hub.core.api import Module, Route

from . import routes

MODULE = Module(
    id="media",
    title="Media",
    screens=("media",),
    lanes=("changed",),
    routes=(Route("GET", "", routes.list_media),
            Route("POST", "/favorite", routes.favorite),
            Route("GET", "/favorite-folders", routes.favorite_folders),
            Route("POST", "/favorite-folders", routes.favorite_folder),
            Route("GET", "/drive", routes.drive_list),
            Route("GET", "/characters", routes.characters_list),
            Route("POST", "/characters", routes.character_put),
            Route("POST", "/characters/rename", routes.character_rename),
            Route("POST", "/characters/remove", routes.character_remove),
            Route("POST", "/characters/notes", routes.character_notes),
            Route("POST", "/characters/voice", routes.character_voice),
            Route("POST", "/keep-voice", routes.keep_voice),
            Route("POST", "/drive/folder", routes.drive_folder),
            Route("POST", "/drive/rename", routes.drive_rename),
            Route("POST", "/drive/move", routes.drive_move),
            Route("POST", "/drive/remove", routes.drive_remove),
            Route("POST", "/move", routes.move),
            Route("POST", "/delete", routes.delete)),
)
