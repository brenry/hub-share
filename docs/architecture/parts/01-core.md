# Part 1 — The core

Scope: everything at `hub/` top level (`hub/__init__.py`, `hub/__main__.py`, `hub/server.py`, `hub/settings.py`,
`hub/settings_edit.py`, `hub/pathrules.py`), `hub/core/*` and `hub/worker/*`, with Stage 6 (continuing a clip),
Stage 7 (Omni references), the Stage 8 lifts (`named.py`, `temp.py`, `checks.py` and `clipplan.py` out of the modules; `job.submitted.by`)
and Stage 9 step 1 (the engine dump and the continue probe). Modules (`hub/modules/*`) appear only
where the core touches them. Citations are `path:line` or `path` + function name. There is no `hub/main.py`,
`hub/runtime.py` or `app.py`: the server wiring lives in `hub/server.py`, and the assembly of services and the ASGI
app lives in `hub/core/runtime.py` (`Core`).

## 1. Process model and startup

### 1.1 What runs

| Process | Program | Started by | Notes |
|---|---|---|---|
| Controller | `python -I -m hub serve --data <DATA>` | systemd user unit `deploy/hub.service` (`ExecStart`, `Restart=on-failure`, `OOMPolicy=continue` at `:15`, `UMask=0077`) | One asyncio event loop; `hub/core/runtime.py:1` says "One event loop, no locks". |
| Engine worker (one per engine GPU) | `<engine python> -B -s -X utf8 hub/worker/main.py --fd N --parent PID --root R --state S [--models D]... -- <engine args>` | `Supervisor._spawn` (`hub/core/supervisor.py:156-185`) on demand | Runs the engine's own Python, stdlib + engine only (`hub/worker/main.py:1`). |

The console entry point is `hub = "hub.__main__:main"` (`pyproject.toml`, `[project.scripts]`).

### 1.2 The `hub` CLI (`hub/__main__.py`)

- The first statement after the docstring imports and installs the network seatbelt, before `argparse` or any
  other import: `from hub.core import netlock; netlock.install()` (`hub/__main__.py:5-7`). A test checks the order
  (`tests/core/test_netlock.py:57`, `test_cli_installs_the_hook_first`).
- Commands (`_parser`, `hub/__main__.py:49-73`; help text `EPILOG`, `:36-46`): `serve`, `init`, `pair --name`,
  `network show|set|reset`, `restart`. Every command takes `--data DIR`, else `$HUB_DATA` (`_data`, `:76-80`).
- `serve` imports `hub.server.run` lazily and returns its exit code (`main`, `:199-202`).
- `init` (`cmd_init`, `:134-160`) writes or updates `settings.json`: `server.bind` = the given address plus
  `127.0.0.1` (`_with_loopback`, `:83-84`), `server.port` (default `PORT` = 42010, `hub/settings.py:23`),
  `engine.root`/`engine.python`, `<root>/ckpts` appended to `engine.model_folders` when it is a directory,
  `modules.loras.folders` from `--lora-folder`, and one `gpus` entry `{"id": "gpu<N>", "index", "uuid", "engine":
  true}` with the UUID read through NVML (`Probes().gpus()`). The data folder is created with mode `0o700`.
- `pair` mints a one-time code and prints `<link_base>/pair#c=<code>` (`:207-211`; `link_base`,
  `hub/settings.py:276-280`).
- `network set` checks each address is numeric, not unspecified (`check_bind`) and bindable on this machine
  (`_check_local`, `:108-114`), saves, then restarts the unit. `network reset` binds the first global IPv4 address of a
  non-virtual, up interface from `ip -j -4 addr show scope global` (`lan_address`, `:117-131`; the `VIRTUAL` name
  prefixes, `:35`) plus loopback, port 42010, no extra hosts, `allow_any_interface=False` (`:206-211`).
- `restart` and the post-save restart touch `<data>/run/restart` and run `systemctl --user restart hub.service`
  (`_restart`, `:123-134`; `_systemctl`, `:116-120`).

### 1.3 `hub serve` (`hub/server.py`)

`serve(data_dir)` (`hub/server.py:103-125`), in order:

1. `load(data_dir)` → validated settings; a `SettingsError` prints one line and returns 1 (`:104-108`).
2. Deletes a stale `run/restart` marker (`:109`) and the data folders of retired modules, `RETIRED_DATA = ("llm",)`
   (`:23`, `:110-111`).
3. `bind(addrs, port)` (`:50-70`) opens one socket per bind address on the same port (`SO_REUSEADDR`;
   `IPV6_V6ONLY` for IPv6). An address that fails is printed with the fix `hub network reset` and recorded as
   `missing`; no socket at all returns 1 (`:113-115`).
4. `build(...)` (`:90-100`): constructs `Core` (`hub/core/runtime.py:69`), wires engines (`wire_engines`,
   `:82-96`: one `engine.create(...)` lane per `gpus[]` entry with `engine: true`; an import or setup failure is a
   `SystemExit` with one line), discovers modules (`registry.discover(settings["modules_disabled"])`, `:105`), prints
   each module load error to stderr, calls `core.load_modules(mods)`, and wraps `core.app()` in `HubServer`.
   `RegistryError` or `ValueError` returns 1 (`:127-129`).
5. `await core.start()` (`:130`), prints exactly `hub started on http://<addr>:<port> ...` (`:132`), then
   `server.serve(sockets=socks)` (`:133`).

The uvicorn configuration (`config`, `hub/server.py:42-47`): `ws="websockets-sansio"`, `http="h11"`,
`lifespan="off"`, ping interval/timeout 15 s, `ws_max_size=1 MiB`, `ws_max_queue=32`, no per-message deflate,
`access_log=False`, `log_config=None`, `log_level="error"`, no `Server`/`Date` headers, `proxy_headers=False`,
graceful shutdown 3 s, `limit_concurrency=64`, `h11_max_incomplete_event_size=16_384`. The module docstring
(`hub/server.py:1-3`) states stdout gets exactly two lines per run plus real errors; `tests/core/test_process.py`
(`test_serve_is_quiet_and_says_going_off`) runs the real process and checks this.

Shutdown: `HubServer.shutdown` (`hub/server.py:33-39`) reads and deletes the `run/restart` marker, calls
`core.stop(restart)`, lets uvicorn finish, then prints `hub stopped`. `Core.stop` (`hub/core/runtime.py:262-279`)
sends `going_off` to every line and closes it with 4001 (restart) or 4000 (off) (`Bus.going_off`,
`hub/core/bus.py:70-74`), closes the session timer, runs module `stop` hooks in reverse order with a 5 s timeout each,
stops busy lanes or releases idle ones (10 s each), closes the dispatcher and flushes every `JsonDoc`
(`Store.flush`).

### 1.4 `Core` assembly (`hub/core/runtime.py`)

`Core.__init__` (`:70-104`) builds, in this order: `Store` and `Events`; `Devices(data_dir)`;
`Bus(devices, boot, VERSION, timing)`; `Files(data_dir, drive_root, characters_root)` (which makes `<data>/outputs` and `<data>/clips`), then
`files.set_storyboards(storyboards_folder(settings))` (`:82-83`); `Delivery(bus, files)`;
`Vram(probes, settings, bus)`; `JobBook(bus, settings, events.emit)`; `Dispatcher(book, vram, bus, files)`;
`McpAccess(store.doc(<data>/core/mcp.json, {"version": 1, "enabled": False}))`; `Gate(devices, hosts(settings,
port))`; `NetworkAdmin(...)`; `engine = NoEngine()`; `Session(...)`. It then links callbacks: presence changes
re-publish cards and drive the session (`:99-101`), the job book asks whether a session is open (`:102`), VRAM changes
re-publish cards (`:103`), and `install_handlers(self)` registers the core bus handlers (`:104`).
`boot` is a fresh `secrets.token_hex(8)` per process (`:73`) and is sent in `welcome`.

`add_engine` (`:112-115`) adds the lane to the dispatcher and makes the first engine `core.engine`.
`load_modules` (`:117-132`) gives each module a `ModuleCtx` with `data_dir = <data>/<module-id>` and
`settings["modules"][<id>]`, registers its tab/sockets for the bus (`bus.tools`), its lanes as `<id>.<lane>` with
default roles `("workspace", *mod.screens)`, its handlers, its job kinds as `<id>.<kind>`, its `listens`, and its
generated MCP tools (`tools_of`). `app()` (`:134-147`) mounts, in order: shell and asset routes (`web_routes`), media
routes (`file_routes`), core routes (`core_routes`), `/mcp`, the `/bus` WebSocket, then each module route at
`/api/<module-id><path>`, and wraps the Starlette app in `Guard`.

### 1.5 The engine worker (`hub/core/engine.py`, `hub/core/supervisor.py`, `hub/worker/*`)

**Lane.** `engine.create` (`hub/core/engine.py:212-229`) builds one `EngineLane` with id `image.<gpu id>`
(`:224`), state folder `<data>/engine/<gpu id>`, and a `Spawn` from `make_spawn`. If the engine Python is not a file
or the engine root is not a directory, the lane starts `down` with the text "The engine's Python or folder is not set
up; run hub init" (`:227-228`). `EngineLane` (`:36`, `EngineLane(CatalogQueries, LaneMemory)`) implements both `api.JobLane`
and `api.Engine` (`:1`). Two mixins hold its halves: the catalog half (`query`, the cache, the fetch from the worker)
is `CatalogQueries` in `hub/core/enginequery.py:17`, whose own docstring says it relies on state `EngineLane` holds
(`:4`; 3.5); what the worker holds between jobs, and when it is stopped to free it, is `LaneMemory` in
`hub/core/enginelane.py:25` (below).

**Spawn** (`hub/core/supervisor.py`):
- Environment (`worker_env`, `:40-46`): only `PATH`, `HOME=<data>/engine-home`, `LANG=C.UTF-8`,
  `CUDA_DEVICE_ORDER=PCI_BUS_ID`, `CUDA_VISIBLE_DEVICES=<uuid or index>`, `LD_LIBRARY_PATH` if set, plus
  `protocol.OFFLINE_ENV`. Nothing else is inherited.
- Command (`_spawn`, `:170-173`): `python -B -s -X utf8 <worker> --fd <child fd> --parent <controller pid>
  <args>`, `pass_fds` only the child end of an `AF_UNIX` `socketpair` (`:166`), stdin `/dev/null`, stdout/stderr
  `/dev/null` unless Diagnostics (`passthrough`, `:168`), `start_new_session=True`.
- Arguments (`worker_args`, `:74-81`): `--root`, `--state`, one `--models` per `engine.model_folders`, `--profile N` only
  when the profile is a number (not `"engine"`, `ENGINE_OWN`), then `--`, then `engine.args`. The profile is
  `engine.profile` unless the caller passes one. `make_spawn` (`:59-64`) uses `engine.profile`. A job on a video model
  passes `job_profile(engine, kind)` (`:67-71`): `engine.profile_video` when the model's catalog `kind` is `"video"` and
  that setting is a number, else `engine.profile` (`profile_video` is `"same"` by default, `SAME`; 5.1). The lane applies
  it before each job (`_follow_profile`, below). The worker parses `--profile` as a float (`hub/worker/main.py:132`) and
  hands it to `Engine` (`:154`, `:205`).
- `OOMPolicy=continue` (`deploy/hub.service:15`): the worker is a child of the Hub's unit. When the kernel takes it
  for memory, systemd leaves the Hub running; the supervisor reports the exit as "Engine stopped unexpectedly (signal
  KILL)" (`exit_text`, `supervisor.py:110-116`), the running job fails with that line and the lane restarts the worker lazily. With
  systemd's default (`OOMPolicy=stop`) the whole unit stopped.
- The worker's own cgroup (`hub/core/enginescope.py`): systemd-oomd kills a whole leaf cgroup, so the worker
  starts through `systemd-run --user --scope` (exec in place: same pid, socket and PDEATHSIG; `env -u` strips
  systemd's variables) when that wrapper works; a memory kill then takes the engine and never the controller.
- Orphans: the pid file `<data>/run/worker-<gpu>.pid` holds `{pid, start}`; `kill_orphan` (`:91-107`) SIGKILLs a
  leftover worker only if pid, `/proc` start time and script path all match.
- States: `none | starting | ready | stopping | down` (`:124`). Ready timeout 600 s (`:121`, `_start_timeout` `:193`).
  Crashes restart lazily with backoff 2/10/30 s (`BACKOFF_S`, `:27`); three crashes within 600 s, or any failure
  while starting, leave the lane `down` until `reset()` (`:28-29`, `_watch` `:224-248`). `engine.start` on the bus
  calls `reset()` on every lane (`hub/core/routes.py:105-110`).
- Stop (`stop`, `:259-278`): send `{"op":"stop"}`, wait 5 s, SIGTERM, wait 3 s, SIGKILL.

**Wire protocol** (`hub/worker/protocol.py`, `PROTO = 2` since Stage 9 step 3): NDJSON over the socketpair, one
object per line, at most `MAX_LINE = 1 MiB`. Controller → worker ops: `run {job, task, request}` (the request in the
Hub's words, a `PictureRequest`, `ClipRequest` or `JoinRequest` plus its `kind`, `hub/worker/engineapi.py`; the worker's
adapter turns it into the engine's task), `cancel {job}`, `query {id, what: "catalog"}`, `stop {}`. Worker → controller
events: `ready` (with `proto`: a worker on another protocol is refused and the lane goes down with "The engine's worker
speaks protocol <n>; the Hub speaks 2 (install the Hub again)", `Supervisor._read`, `OTHER_PROTO`), `fatal`, `model`,
`progress`, `output`, `task_done`, `reply` (the module docstring). Before a job's first task is sent, every task is
parsed as the worker will parse it (`enginelane.checked`, `enginewire.request_parse`: its kind, its fields, a picture's
role among those its kind takes); one that fails is "Task <k> is not a request the engine takes: <line>" (stage
`runtime`) and the worker is neither started nor sent anything. An oversized or non-JSON line kills the worker (`Supervisor._read`, `:205-222`; worker side
`os._exit(2)`, `hub/worker/main.py:85`).

**Worker side** (`hub/worker/main.py:main`, `:187-217`): `os.environ.update(OFFLINE_ENV)`,
`sys.dont_write_bytecode = True`, `netguard.install()`, then, by flag, one of three one-shot modes or the serving loop.
`--dump-engine OUT.json` (`dump_engine`, `:170-184`) opens the engine on an empty state folder and writes its facts as
sterile JSON (`enginedump.write`; part 5, 5.2.6); `--dump-catalog OUT.json` (`dump`, `:151-167`) writes the model
catalog; `--probe-continue CLIP` (`probe.run`, `hub/worker/probe.py:96`) runs continue steps and prints one JSON line
each. The three take no `--fd` and no `--parent`, and `parse` (`:121-148`) refuses `--dump-engine` together with
`--models`, `--profile` or `--dump-catalog`, and `--probe-continue` without `--state` or with `--chain` below 1. The
serving loop calls `die_with_parent` (`prctl(PR_SET_PDEATHSIG, SIGKILL)` and an exit if the parent pid already
changed, `:61-67`). EOF or any send failure on the socket exits at once (`Link.send`, `:52-59`; `serve`, `:70-99`). A
second `run` while busy answers `task_done ok:false "The engine is busy"` (`:93`).
`tests/engine/test_rules.py:38` (`test_worker_is_stdlib_only`) restricts worker imports to the stdlib plus its sibling
files and `adapters`; `:59` (`test_no_engine_key_family_outside_the_adapters`) fails when an engine key family or a model
name appears in any `hub/**` file outside `hub/worker/adapters/`; the model-name guard
(`tests/engine/test_video_engine.py:138`, `test_core_and_worker_name_no_model`) still covers `hub/core` and the worker's other files.

**Offline guard.** `OFFLINE_ENV` (`hub/worker/protocol.py:29-38`): `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`,
`HF_HUB_DISABLE_TELEMETRY=1`, `DO_NOT_TRACK=1`, `GRADIO_ANALYTICS_ENABLED=False`, `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONNOUSERSITE=1`, `PYTHONUNBUFFERED=1`. `netguard._hook` (`hub/worker/netguard.py:27-41`) is a `sys.addaudithook`
hook that raises `PermissionError` for `socket.connect/sendto/sendmsg` to anything but `AF_UNIX` or a loopback IP,
for `getaddrinfo/gethostbyname/gethostbyname_ex` of a non-numeric host, and for reverse lookups of non-loopback
addresses. Its docstring notes native code can bypass audit hooks (`:3-4`).

**What is forced on the engine** (`hub/worker/wgpconfig.py` for the config file; `hub/worker/adapters/fork.py` and `upstream.py` for the task, 5.6 in part 5):
- `FORCED_CONFIG` (`wgpconfig.py:18-20`): `image_output_codec="png"`, `metadata_type="none"`, `enhancer_enabled=0`,
  `enhancer_mode=1`, `enabled_plugins=[]`, `save_queue_if_crash=0`, `embed_source_images=False`, and
  `video_container="mp4"` (a clip is an MP4 whatever the engine config says). Applied to the seeded config file
  (`seed_config`, `wgpconfig.py:56-90`, the update at `:76`) and again to the live `server_config` after start
  (`Engine.open`, `wan2gp.py:148`). `wan2gp.py` re-exports it (`:32`).
- `DROPPED_CONFIG` (`wgpconfig.py:17`): `services`, `llm_engines`, `enabled_plugins`, `installed_remote_plugins`, plus
  every `notification_*` key, removed when the engine's `wgp_config.json` is copied (`:73-75`).
- `PROFILE_KEYS` (`wgpconfig.py:24`): when a memory profile is picked (Settings → Engine), `seed_config` writes it
  under `profile`, `video_profile` and `image_profile` (`:77-78`); with no pick the engine config's own stays (see 5.3).
- `FORCED_TASK` (`adapters/fork.py:24-26`, `adapters/upstream.py:22-23`, the same values): `prompt_enhancer=""`, `negative_prompt=""`,
  `alt_prompt=""`, `output_filename="{date}-{seed}"`, laid over every task's settings by the adapter's `translate`
  (`fork.py:45-54`, `upstream.py:47-50`; called from `Engine._params`, `wan2gp.py:166-172`).
- `FORCED_VIDEO`, laid over a task whose `image_mode` is 0, that is a clip (each adapter's `translate`): the clip keeps
  the sound its model makes and never gets a soundtrack or a second audio model. The fork's is `audio_prompt_type=""`,
  `MMAudio_setting=0` (`fork.py`); upstream's is `audio_prompt_type=""`, `postprocess_audio=""` (`upstream.py`;
  `MMAudio_setting` is deprecated there, accepted and ignored, so it is never sent; R16 §3.4). A picture task
  (`image_mode` 1) is unchanged. Upstream's `translate` also refuses, in one line, any key outside the settings the
  engine accepts (`accepted_setting_names`, when the engine has that call; R16 §1).
- The clip guard (`Engine.run`, `wan2gp.py:223-231`): after a clip task the peak resident memory is read as the process's
  high-water mark (`VmHWM`, `rss_mb`, `:53-62`; `Peaks.sample(final=True, mark=clip)`, `:90-102`), and when the engine's
  chained passes (a continue, a scene longer than one window) left several files, the last one is kept and the earlier
  ones are deleted, because each file holds the ones before it (`:227-231`).
- The engine's config, outbox and per-model settings live in the lane's state folder, not the engine root
  (`wan2gp.py:1-8`, `open`, `:124-149`); the outbox and settings folders are emptied and `queue.zip`/`error_queue.zip`
  deleted at each start (`:128-136`). The engine's `get_lora_dir` is replaced by `catalog.lora_dir`, which "never
  creates folders" (`:145-146`). The first checkpoint search path is a hub scratch folder, so the engine never writes into
  the model folders (`search_paths`, `wgpconfig.py:38-53`).

**Running a job on a lane** (`EngineLane.run`, `hub/core/engine.py`). Under the lane lock `run` checks every task as
the worker will parse it (`enginelane.checked`), reads the job's model kind and, unless the job was cancelled while
queued, calls `_before` and then `_ensure`. The pieces are `LaneMemory` (`hub/core/enginelane.py`, module docstring `:1-12`):
- `_kind` (`:43-49`): the `kind` of the job's model in the catalog (`cached_catalog`, memory or the cache file); when
  the catalog has no such model, `video` if every task is a clip (`image_mode` 0), else None.
- `held()` (`:39-41`): the model the running worker holds: `_resident`, the model of the last task sent to it
  (`_task` sets it right after it sends `run`, `engine.py:159`; an `exit` event clears it, `:194`), else the model the
  worker reported; None when no worker runs. A worker that has only started holds nothing.
- `_before` (`:60-65`): `_follow_profile`, then `_unload` when the worker holds a model other than the job's. The same
  model is never released. `_follow_profile` (`:72-82`) builds the worker arguments with `job_profile` for the
  model's kind; when they differ from the arguments the lane's `Spawn` has, it takes the new ones and stops a running
  or starting worker, so a clip after an image with two different profiles restarts the worker, and with
  `profile_video` at `same` nothing restarts. `_unload` (`:51-58`) stops the worker, waits for it to exit, clears
  `_resident` and emits `model {state: "released", model}`.
- `_after` (`:67-70`): after a job whose model is a video kind, made or failed, the worker is stopped, so a clip's
  memory goes back at once. In `run`'s `finally` (`engine.py:120-127`) a restart asked by a settings change
  (`_restart`, set by `configure`) stops the worker instead; then `on_change` publishes the lane.
Every model switch and every clip therefore costs a worker restart and a full model load; two jobs on the same
picture model in a row cost neither. `_ensure` (`engine.py:144`) starts the worker if needed. For each task the lane
emits `task`, sends `run`, and translates worker events (`_task`, `:155-182`): `model` → `model`; `progress` →
`progress` with `pct` over the whole job (`enginecat.progress`, `hub/core/enginecat.py:72-80`); `output` →
`enginecat.land` (run in a thread, given the outbox, the Temp folder `<data>/outputs` and the clips folder `<data>/clips`,
`engine.py:169-170`) → `output {task, item, kind, w, h}` (`:171`), with `seconds` added for a
clip; `task_done` → `task_done {task, seconds, model, peak_vram_mb, peak_rss_mb}`, then sweep the outbox
(`enginecat.sweep`, `:97-103`) so nothing of a task stays behind; `exit` → `EngineFailed`. A failed or cancelled task
raises `EngineFailed(stage, text)` (`hub/core/supervisor.py:32-37`).

**Landing a file** (`land`, `hub/core/enginecat.py:119-159`). The worker names the file; `land` accepts it only if it
is a file directly in the lane's outbox (else `EngineFailed("runtime", "The engine wrote an image outside its
outbox")`, `:126-128`) and sorts it by its extension (`files.CLIP_TYPES` is `.mp4` only, `files.IMAGE_TYPES` the picture
types):
- An MP4 (`:130-142`): `clip.strip(path)` cuts the tags the muxer wrote, `clip.facts(path)` reads its size and length
  from its boxes, the frames are never decoded; either failing deletes the file and fails the job with "The engine wrote
  a clip the hub could not read". The file is hard-linked (`link_or_copy`, `:82-94`, a copy across filesystems) to
  `<clips>/<day>/<time-name>.mp4` and the outbox copy is removed. Result `{id: "clips/<day>/<name>.mp4", kind: "clip", w, h, seconds}`.
  Every clip lands flat in the day folder, a continued one too: the plan names no folder, and the code that once
  let a continue land in its source's group folder (`JobPlan.land_in`, `group_folder`) is gone.
- A picture (`:146-159`): `clean.strip` cuts its metadata, then it lands in `<data>/outputs` the same way; width and
  height come from Pillow (`None` when unreadable). Result `{id: "out/<day>/<name>", kind: "image", w, h}`.
- Anything else is deleted and fails the job with "The engine wrote a file the hub does not take" (`:143-145`).
The name is the landing time (`files.temp_path`); the id carries no prompt, seed or model.

**The clip file** (`hub/core/clip.py`, module docstring `:1-16`). `strip` (`:40-46`) walks the MP4 as ISO-BMFF boxes and
never decodes it. It removes every `udta` box (top level, inside `moov`, and inside its tracks and their media boxes) and
a `meta` box directly under `moov` (`_children`, `:211-227`), so encoder tags (`©too`, `©cmt`, `ilst` items) are gone.
Only `moov` is read into memory (`_movie`, `:113-123`; larger than `MOOV_CAP` = 256 MiB is refused, `:27`); the other
boxes are streamed to a `.<name>.clean` temp file, which then replaces the original (`_strip`, `:126-150`; the temp file
is deleted if the copy fails). Parent box sizes are fixed, a 64-bit header keeps its form (`_boxhead`, `:245-251`), and
the chunk offset tables (`stco`/`co64`) are rewritten to follow the data when a box ahead of `mdat` shrank (`_mover`,
`:188-201`; `_offsets`, `:230-242`; an offset outside the media data raises). A fragmented file (`moof`, `mfra`, `sidx`,
`ssix`: `FRAGMENTS`, `:26`) has offsets the walk does not rewrite, so each cut box becomes a zeroed `free` box of the
same size and nothing moves (`:130`, `:141-143`, `:218-219`). A file whose boxes do not tile, that has no `ftyp` first
or not exactly one `moov` raises `ValueError` (`_top`, `:172-185`). `facts` (`:49-65`) reads the same walk: the first
video track's size from `tkhd` (16.16 fixed point), `fps` and `seconds` from `mdhd` and the frame count from `stts`
checked against `stsz` (`_video`, `:69-89`; a disagreement or a zero raises), and `audio` true when any track's
handler is `soun`. Result `{w, h, fps, frames, seconds, audio}`.

## 2. The module system

### 2.1 The contract (`hub/core/api.py`)

The file says it is "the ONLY core file a module may import" and is stdlib only (`hub/core/api.py:1-6`).

| Name | Kind | Fields / methods | Line |
|---|---|---|---|
| `Kind` | Literal | `image, video, audio, mask, text` | `:15` |
| `Auth` | Literal | `screen, public` | `:16` |
| `Invalid(field, text)` | Exception | becomes HTTP 400 / bus `error` `{field, text}` | `:22-27` |
| `Tab` | dataclass | `label, order` | `:32-34` |
| `SocketGroup` | dataclass | `id, label, kinds, max` | `:38-42` |
| `Route` | dataclass | `method, path, fn(ctx, request), auth="screen", body_limit=65_536`; mounted at `/api/<id><path>` | `:46-52` |
| `CardState` | dataclass | `summary, status` (`ok/attention/off/error`) | `:56-58` |
| `Card` | dataclass | `title, order, state(ctx) -> CardState` (sync, from memory) | `:62-66` |
| `SettingKind` | Literal | `choice, number, integer, text, loras, seed, names` | `:69` |
| `Setting` | dataclass | `name, kind, choices=(), lo, hi, text` | `:73-85` |
| `Screen` | dataclass | `settings, read(ctx), write(ctx, partial)` | `:89-93` |
| `Listing` | dataclass | `name, text, args (JSON Schema properties), fn, required=()` | `:97-103` |
| `Action` | dataclass | `name, text, schema, fn` | `:107-112` |
| `JobPlan` | dataclass | `lane_kind, model, tasks, summary`; `inputs` (task k's fields an earlier task's file fills: `"file"`, `"kept"`, or `"best"`, the shot's best take), `prepare`, `finish`; `takes` (per shot, its takes, each its tasks in order) and `judge` (the job's judge step) | `:100-111` |
| `Take`, `Judge` | dataclass, Protocol | `Take(passes, rank, line)`; `Judge.done(task, d) -> Take | None` on each take task's `task_done` (the dispatcher), `Judge.again(shot, take)` read by the lane before a re-take (`jobgraph.runs`; a skipped take is the lane event `skip`; a failed re-take a `Take` with no rank, `jobgraph.absorbs`) | `:113-122` |
| `Module` | dataclass | `id, title, tab, screens, sockets, routes, handlers, lanes, jobs, listens, card, screen, listings, actions, start, stop` | `:126-143` |
| `Device`, `Resident`, `Job` | records | `Job`: `id, kind, tool, state, plan, lane, task, pct, eta_s, error, outputs, notes, takes` (task -> its `Take`) | `:145-170` |
| `JobLane` | Protocol | `residency, busy, pids, release, ready, reset, run(job, emit), cancel, stop` | `:175-194` |
| `JsonDoc`, `Files`, `Bus`, `Jobs`, `Engine` | Protocols | services carried by `Ctx`; `Jobs.submit(kind, params)` takes no `by` (the module's context adds it, 3.4) | `:197-250` |
| `Ctx` | Protocol | `module_id, data_dir, settings, files, bus, jobs, engine, doc(), emit()` | `:252-261` |
| `whole`, `number`, `seed_value`, `seeds`; `clip_facts`, `snap_frames`, `frames_for`, `tier_size` | functions | pure helpers a module may call, re-exported from `hub/core/checks.py` (`:12-50`) and `hub/core/clipplan.py` (`:15-60`); `best_take` (`hub/core/takeplan.py`, the rule `jobgraph.fill` reads for `"best"`); imported at the end of the file | `:274-280` |

`Setting` semantics (docstring, `:74-79`): `choice` with no `choices` is any text checked by the screen's `write`;
`number`/`integer` with `choices` is one of them; `text` is free text, at most `hi` characters; `loras` is a list of
`{id, strength lo..hi}`; `seed` is `"random"` or a whole number `lo..hi` as text; `names` is at most `hi` names. "Every
bound is the module's: `lo` and `hi` here, nothing in the core."

### 2.2 Import rules

- Modules import only `hub.core.api` (or `hub.core`) and their own package: `tests/core/test_rules.py:57-64`
  (`test_modules_import_only_the_api`). A stricter form for `generate_image`, `loras`, `media` (only
  `hub.core.api`): `tests/engine/test_rules.py:72-78` (`test_modules_reach_core_only_through_the_api`).
- Core never imports modules: `tests/core/test_rules.py:67-70` (`test_core_never_imports_modules`) checks
  `hub/*.py` and `hub/core/*.py` for `hub.modules` imports. Modules are found only by `registry.discover`, which
  imports `hub.modules.<folder>.manifest` by name at run time (`hub/core/registry.py:41`).
- Front end equivalent: `src/modules/*` import only `react`, `ui/`, `lib/` and their own folder
  (`web/tests/unit/guards.test.ts:71-81`).

### 2.3 Discovery and validation (`hub/core/registry.py`)

`discover(disabled)` (`:33-52`): every non-hidden, non-underscore folder under `hub/modules` that has a `manifest.py`,
in sorted folder order. An import failure or a missing `MODULE` adds one error line (`hub: module <folder> was not
loaded: ...`) and skips that folder; ids listed in `modules_disabled` are skipped; then `validate(mods)` runs and
any rule break raises `RegistryError`, which stops the hub (`hub/server.py:118-120`).

`validate` rules (`:71-119`):
- Module id matches `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$` (`ID`, `:18`) and is not in `RESERVED` = `api, assets, bus,
  cards, core, files, upload, mcp, pair, screen, settings, thumbs` (`:24-25`); ids are unique.
- Socket group ids unique and `^[a-z0-9_]{1,40}$` (`NAME`, `:19`); kinds non-empty and within `KINDS`; `max >= 1`.
- Routes: no duplicate `(method, path)`; method in `GET/POST/PUT/PATCH/DELETE`; path empty or starting with `/`;
  auth `screen` or `public`; `0 < body_limit <= 25 MiB` (`MAX_BODY`, `:26`).
- Handlers named `<id>.<snake_name>`; lanes and job kinds are `NAME` matches.
- Screen settings: non-empty, unique `NAME` names; kind in `SETTING_KINDS`; choices allowed per kind (`_choices_ok`,
  `:55-61`: `choice` → strings, `number`/`integer` → non-bool numbers, others → none); bounds (`_bounds_ok`,
  `:64-68`: `names` needs `hi >= 1`; `seed` and `loras` need `lo < hi`).
- Generated tools (`tools_of`): name matches `^[a-z][a-z0-9_]{0,63}$` (`TOOL`, `:20`), unique across all modules,
  schema is a dict, description non-empty, at most 200 characters, ending with `.` (`:114-119`).

### 2.4 MCP tools generated from declarations (`hub/core/features.py`)

`tools_of(mod)` (`:93-98`) returns, in order: the screen's get and set, then one tool per listing, then one per
action. Nothing is hand-written per feature (`:1-6`).

| Declaration | Tool name | Description | Input schema | Calls |
|---|---|---|---|---|
| `Screen` | `get_<id>_settings` (`-` in the id becomes `_`, `:66`) | `Settings of the <title> screen: <names>.` | `NO_ARGS` (`{}` object, no extra properties, `:14`) | `screen.read(ctx)` |
| `Screen` | `set_<id>_settings` | `Set settings of the <title> screen: <names>. Returns the settings after.` | object, `additionalProperties: false`, one `value_schema(s)` per setting, nothing required | `screen.write(ctx, args)` |
| `Listing` | `list_<name>` | `listing.text` | object of `listing.args`, `additionalProperties: false`, `required` if given | `listing.fn` |
| `Action` | `<name>` | `action.text` | `action.schema` as declared | `action.fn` |

(`_screen_tools`, `:65-79`; `_listing_tool`, `:82-86`; `_action_tool`, `:89-90`.)

`value_schema(s)` per kind (`:36-62`):

| Kind | Schema |
|---|---|
| `choice` | `{"type": "string"}`, plus `enum` when `choices` |
| `text` | `{"type": "string"}`, `maxLength = int(hi)` when `hi` is set |
| `number` / `integer` | `{"type": "number" \| "integer"}`, `minimum = lo`, `maximum = hi` when set, `enum` when `choices` |
| `loras` | `{"type": "array", "items": lora_schema(lo, hi)}`; each item `{id: string minLength 1, strength: number lo..hi, file: string readOnly}`, required `id, strength`, no extra properties (`:26-33`) |
| `names` | `{"type": "array", "maxItems": int(hi), "items": {"type": "string", minLength 1, maxLength 120}}` |
| `seed` | `{"type": "string", "minLength": 1, "maxLength": len(str(int(hi)))}`; description becomes `<text>: random, or a whole number from <lo> to <hi>` |

`description` is the setting's `text` when present.

### 2.5 Argument checking (`hub/core/schema.py`)

`check(schema, args)` (`:15-23`) is what `/mcp` runs before every tool call (`hub/core/mcp.py:164`). Supported
keywords (`:1-6`): `type` (object, string, integer, number, boolean, array), `required`, `properties`,
`additionalProperties` (false or a schema), top-level `default`, `enum`, `minLength`, `maxLength`, `minimum`,
`maximum`, `multipleOf`, `maxProperties`, `minItems`, `maxItems`, `items`. Rules:

- `null` arguments are `{}` (`:17-18`).
- A `null` value for a known, not-required property is dropped, the same as leaving it out (`_object`, `:38-39`);
  this applies to every object level checked by `_object`.
- An unknown key with `additionalProperties: false` is `Invalid(key, "unknown argument <key>")` (`:42-43`).
- For `integer`, a float with `is_integer()` becomes an `int` (`:63-64`); booleans are never numbers (`:66`).
- Top-level `default`s fill missing properties after validation (`:20-22`).
- Every failure is one `Invalid(path, text)` line, returned to the MCP client as `isError: true` text
  (`hub/core/mcp.py:166-167`).

Tests: `tests/core/test_mcp.py:267` (`test_schema_takes_null_as_left_out_and_a_whole_float_as_an_integer`).

## 3. Services in `Ctx`

`ModuleCtx` (`hub/core/context.py:87-110`) implements `api.Ctx`. `data_dir` is created (`:92`); `settings` is a
read-only `MappingProxyType` deep copy of `settings["modules"][<id>]` (`:93`), replaced after a settings edit
(`hub/core/apply.py:39-40`). It also carries `network` (`NetworkAdmin`) and `mcp` (`McpAccess`), used by the Network
and Assistant modules (`:1-4`, `:97-98`).

### 3.1 JsonDoc (`hub/core/store.py`)

- `ctx.doc(name, default)` → `<data>/<module-id>/<name>.json`; `name` must match `^[a-z0-9][a-z0-9_-]{0,40}$`
  (`hub/core/context.py:21`, `:104-107`). One `JsonDoc` per path, owned by `Store` (`hub/core/store.py:112-125`).
- `get()` returns a deep copy; `patch(changes)` is a shallow merge; `replace(value)` replaces (`:65-75`).
- Writes are debounced 0.3 s (`DEBOUNCE_S`, `:14`) and run in the default executor; outside an event loop they are
  written at once (`_schedule`, `:77-86`). A version counter keeps an older snapshot from overwriting a newer one
  (`_write`, `:94-98`). A failed write prints one stderr line (`_report`, `:100-102`).
- `write_json` (`:17-36`): temp file in the same folder, `fchmod` (default `0o600`), `fsync`, `os.replace`, then
  `fsync` on the directory. `read_json` returns `None` for a missing file and raises `ValueError` with one line for
  bad JSON (`:39-48`).
- `Store.flush()` at shutdown writes every unsaved doc (`hub/core/runtime.py:279`).

### 3.2 Files (`hub/core/files.py`, `drive.py`, `characters.py`, `thumbs.py`, `clean.py`)

**Roots and ids.** `roots` (`_build`, `hub/core/files.py:93-100`): `out` = `<data>/outputs` (Temp, created at start,
always present), `clips` = `<data>/clips` (the clips root, created at start, always present; `CLIPS`, `:27`;
`Files.__init__`, `:66-77`), `drive` = `paths.drive` once chosen, `chars` = `paths.characters` once chosen. A fifth
setting is not a root: `Files.storyboards` (`:75`, set by `set_storyboards`, `:89-91`) is a folder name inside the Drive
that `named.py` reads (below). An item id is `<root>/<relative path>`; a clip's is `clips/<day>/<time>.mp4` (a clip
in a folder under its day has that folder in its id). `resolve` (`:102-113`) refuses ids shorter than 3 or
longer than 512 characters, NUL, backslash, a leading `/`, an unknown root, empty/`.`/`..` segments, and any real path
(symlinks followed) outside the root or equal to it; every refusal is `Invalid("item", "That image is no longer
available")` (`GONE`, `:29`; the text still says "image" for a missing clip). Lookups sit on top:
- `existing_image` (`:115-119`) requires a regular file that is a picture (`kind` "image"); it is what the reference
  boxes, `/api/media/check` and the Drive use, so a clip can never be a reference.
- `existing_media` (`:121-126`) requires a regular file of any kind: a picture, or a clip. `GET /files` and `delete`
  use it.
- `clip_facts` (`:128-134`): what `clip.facts` reads from a clip that is there (`{w, h, fps, frames, seconds, audio}`),
  else None for a picture, a missing file or boxes that do not read; a continue uses it for the source clip's size.
- `item_for` (`:136-142`): the item id of a file inside a media root, else None.
- `kind` (`:144-149`): "clip" for an `.mp4` under `clips/` (`CLIP_TYPES = {".mp4": "video/mp4"}`, `:25`); "image" for a
  `.png/.jpg/.jpeg/.webp` anywhere else (`IMAGE_TYPES`, `:24`); None for anything else, including a picture under
  `clips/` or an MP4 outside it.
`url` = `/files/<id>?v=<mtime_ns>` (`:157-158`). `thumb_url` = `/thumbs/<id>/<size>?v=<mtime_ns>` for a picture and None
for a clip (`:160-164`): the hub makes no thumbnail of a clip, and `thumbnail` refuses one with "A clip has no
thumbnail" (`:272-273`). The same three, and the lookups, are on the `api.Files` protocol modules see
(`hub/core/api.py:203-234`); beyond the ones listed here it carries `regroup`, `file_clip`, `newest_temp` and the
named-picture calls (`put_picture`, `rename_picture`, `picture_text`, `picture_text_set`, `:228-233`) and the six
sequence calls (`sequences`, `sequence`, `sequence_new`, `sequence_save`, `sequence_rename`, `sequence_delete`,
`:237-242`; the work is `hub/core/sequences.py`, Stage 11). `sequence_save` is a compare-and-swap on `revision`; no
sequence call moves, copies or erases a clip.

**Temp names.** `temp_path` (`:35-46`): `<outputs>/<YYYY-MM-DD>/<HHMMSS-mmm>[-n]<ext>`, the day folder created if missing
(it takes no folder argument); "The name is the time, nothing else."

**Start-up erase.** `forget_older_records` (`:54-64`), called from `Files.__init__`, deletes `OLDER_RECORDS`
(`inputs`, `cache`, `media/favorites.json`, `loras/covers`, `loras/thumbs`, `core/learned.json`,
`generate-image/prompts.json`) and any dot-file under `outputs` and under `clips` (a half-taken upload, a half-written
clip; `:61-64`).

**Taking a picture in.** `take_in(tmp, suffix)` (`:166-175`) runs `clean.strip(tmp)` then moves it to a `temp_path`.
Engine pictures take the same route through `enginecat.land` (`hub/core/enginecat.py:119-159`); engine clips go to the clips root (below).

**Metadata cut** (`hub/core/clean.py`): `strip(path)` (`:27-39`) keeps only listed PNG chunks (`PNG_KEEP`, `:20-21`),
JPEG segments except APPn other than JFIF/ICC/Adobe and COM, and everything up to EOI (`_jpeg`, `:107-140`), and
WebP chunks except `EXIF`/`XMP ` with the VP8X flags cleared (`_webp`, `:143-161`). A file that does not parse, or a
photo with a non-upright EXIF orientation, is re-encoded from pixels (`_rewrite`, `:51-66`; JPEG quality 95).

**Delete / move / regroup / file a clip.**
- `delete(ids)` (`:180-191`): unlinks each existing picture or clip (Temp, clips, Drive or Characters roots all resolve
  through `existing_media`) and drops its thumbnails; no trash.
- `move(ids, to)` (`:193-211`): into a Drive folder (`drive.folder`), a taken name gets `name (2)`, `name (3)`…
  (`drive.free_name`, `hub/core/drive.py:64-72`); returns `(old id, new id)`. Any clip in `ids` refuses the whole call:
  "Clips stay in the clips folder for now" (`:196-197`).
- `regroup(ids, group)` (`:213-214`, the work is `temp.regroup`, `hub/core/temp.py:28-51`): Temp items only
  (`parts[0]` is `out`; anything else is skipped), into `<day>/<group>/` (or back to `<day>/` for `""`), removing an
  emptied group folder (Favorites is such a folder, 3.3.2). A name taken in the target gets a numbered one (`drive.free_name`).
- `file_clip(item_id, group, name)` (`:216-217`, `temp.file_clip`, `hub/core/temp.py:61-78`): moves a clip of the clips
  root into a named folder under its day (`<group>/<name>.mp4`; the storyboard's skeleton is its one intended caller, and
  the storyboard stage, when built, drops that use); `group` and `name` are plain names (`drive.name_ok`, else `Invalid`
  "Use a plain group name, without slashes"); a name taken by another file becomes `<name>-2`, `-3`; a non-clip is
  refused with "That is not a clip". The day stays the clip's own.
- `newest_temp()` (`:219-220`, `temp.newest_temp`, `hub/core/temp.py:87-102`): the newest picture in Temp by its day
  folder, then its time name (`_time_key`, `:81-84`), whatever group it sits in; hidden files are skipped; None when
  Temp holds no picture. The module docstring (`temp.py:1-6`) notes a name that is not a time sorts first.

**Clips.** A clip is only its frames and sound, and lives in the clips root. `enginecat.land` (`hub/core/enginecat.py:119-159`)
moves an engine's `.mp4` there after `clip.strip` (tags cut) and `clip.facts` (size and length read), under a
`temp_path(clips_root, ".mp4")` name, and returns `{id: "clips/<day>/<time>.mp4", kind: "clip", w, h, seconds}`; 1.5 describes
it and `hub/core/clip.py` box by box. The Hub does nothing else to a clip: no thumbnail (`thumb_url` None), no copy to the
Drive (`move` refuses), no use as a reference (`existing_image`), no favourite. A continue lands its result flat
beside its source, which stays where it is (1.5). A clip is served by `GET /files/<id>` as
`video/mp4` with Range (4.1). Pinned by `tests/core/test_clips.py` (kinds, URLs, delete and regroup, naming, landing and
the tag cut: `test_tags_are_cut_and_offsets_follow_the_data_when_moov_comes_first`,
`test_a_fragmented_clip_keeps_every_byte_in_place`, `test_an_untagged_clip_is_not_rewritten`,
`test_a_file_that_is_not_an_mp4_is_refused`, `test_a_tagged_clip_lands_without_its_tags`),
`tests/core/test_clips_facts.py` (`facts`, and `land` reporting size and length) and `tests/core/test_clips_http.py`
(Range, the `/clips` shell, the media listing, delete).

- Drive folders (`hub/core/drive.py`): `listing`, `make`, `rename`, `move` (1–100 folders, never into itself), `remove`
  (erases the folder tree, drops thumbnails). Paths are relative posix with no empty/`.`/`..`/hidden segments, checked
  by real path (`_rel`, `:25-31`; `folder`, `:52-61`). Without a Drive, `listing` returns `{"unset": true}` and other
  calls raise `Invalid("path", "Choose the Drive folder in Settings → Storage")` (`:22`, `:45-49`, `:77-78`).

**Named pictures** (`hub/core/named.py`; module docstring `:1-12`). A named picture is a file whose stem is its name,
kept at the top of a folder set in Settings: Characters (`chars/<file>`) or a Drive folder (`drive/<path>/<file>`).
`named.py` holds the work Characters and any other such folder share:
- `pictures` (`:32-40`) lists the pictures at the top of a folder, newest first, so a name held by two files
  (`Character 1.png`, `Character 1.jpg`) is the newer one's; `named` (`:43-45`) filters by stem, any case.
- `folder_of` (`:54-63`) accepts `"chars"` or `"drive/<relative path>"` and returns the real folder with its id prefix;
  anything else is refused with `NOT_YOURS`, "That is not a folder of named pictures (Characters, or a Drive folder)"
  (`:25`). `own` (`:66-76`) resolves a named picture that is there, else "That picture is not in its folder now".
- `put` (`:139-165`) copies a picture in as `<name>.<its type>` (`drive.name_ok` checks the name), cuts its metadata
  (`clean.strip`; an unreadable picture is "That image could not be read"), replaces every picture of that stem, and
  carries the replaced picture's text over to the new file where the folder allows text. A picture already named so in that
  folder is returned as it is.
- `rename` (`:168-182`) gives the file the new stem, keeping its type and text and erasing an older file under the old
  stem; a stem another picture of the folder has is refused with the caller's `taken` text (default "A picture in that
  folder is already called <name>").
- The text field, the one thing the Hub writes into a picture. `text_allowed` (`:79-99`) is true for `chars/<file>` at the
  top of Characters and, once `paths.storyboards` is set (`Files.set_storyboards`, `files.py:89-91`; 5.1), for
  `drive/<storyboards>/<name>/<file>` exactly one level under that folder, checked by real path. `read_text`
  (`:102-109`) gives "" elsewhere, for a non-PNG and for an unreadable file; `write_text` (`:112-124`) saves the
  picture again as `<stem>.png` (`pngtext.write`) and erases an older file of the stem; `set_text` (`:127-136`) refuses
  a place that cannot hold text ("That picture cannot hold text") and text over `pngtext.MAX` = 16 384
  (`pngtext.py:16`). `pngtext.py` is the only writer of picture text: `read` (`:19-28`), `write` (`:31-50`), pinned by
  `tests/core/test_rules.py:test_only_pngtext_writes_picture_text`, which walks every `hub/` file for `PngInfo`,
  `add_itxt`, `add_text`, a `pnginfo=` keyword and `PngImagePlugin` imports.

**Characters** (`hub/core/characters.py`): a character is one picture at the top of `paths.characters`; its name is the
file stem, matched case-insensitively; when two files share a stem the newer wins (`listing`, `:38-47`; `find`,
`:49-52`). The file keeps the listing and the policy and calls into `named`: `put` (`:55-58`) is `named.put` into
`"chars"`; `rename` (`:72-76`) checks the id (`_own`, `:61-69`) and calls `named.rename` with "A character is already
called <name>" (`TAKEN`, `:32`); `remove` (`:79-85`) erases the file and any older file of that name; `set_notes`
(`:88-`) checks the text (a string without NUL, at most 1000 characters, `MAX_NOTES`, `:31`) and calls
`named.write_text`. Notes are the one metadata the hub writes into a character's picture: an iTXt chunk `Description`
(`NOTES_KEY` = `pngtext.KEY`, `:29`); the notes belong to the name, so a rename and a new picture put under the name
keep them. `clean.strip` removes the field from any picture coming in under a new name (`:12-13`). Tests:
`tests/core/test_pngtext.py`, `tests/core/test_named.py`, `tests/core/test_temp.py`.

**Thumbnails** (`hub/core/thumbs.py`): `ThumbStore` is an in-memory LRU of WebP bytes capped at 256 MB (`CAP_MB`,
`:16`); keys are `<path>|<mtime_ns>|<size>` (`hub/core/files.py:275`), so a changed file gets new keys; `forget(prefix)`
drops a file's thumbnails (`:49-53`). Allowed sizes `96, 336, 1024` (`THUMB_SIZES`, `hub/core/files.py:28`). Render
refuses images over 64 MP (`MAX_PIXELS`, `:18`), applies EXIF orientation, saves WebP quality 80 (`render`,
`:69-90`). Pillow's decompression-bomb warning is turned into an error at import (`hub/core/files.py:31-32`).

**Changing roots live.** `set_drive` / `set_characters` (`files.py:79-87`) repoint the roots and `set_storyboards`
(`:89-91`) names the storyboards folder; nothing is moved (`hub/core/apply.py:26-33`).

### 3.3 Bus (`hub/core/bus.py`, `line.py`, `messages.py`)

- One WebSocket "line" per screen, keyed by its `screen` id; a second hello with the same id closes the old line with
  4009 (`_hello`, `hub/core/bus.py:154-156`). Roles: `workspace`, `media`, `aux` (`hub/core/messages.py:16`).
- Core lanes: `presence, focus, jobs, gpu, media, settings` (`CORE_LANES`, `messages.py:17`). Default subscriptions per
  role (`DEFAULT_LANES`, `:18-22`): workspace → presence, jobs, gpu, settings; media → presence, focus, media, jobs
  (the judges' verdict on the clip shown), settings; aux → presence, focus, settings. Module lanes `<id>.<lane>` are added to the defaults of `workspace` and
  of each role in `mod.screens` (`default_lanes`, `bus.py:104-105`; `hub/core/runtime.py:123-124`). `sub`/`unsub`
  accept only known lanes (`_lanes`, `bus.py:243-247`).
- `publish(lane, type, data, key)` (`:44-48`) sends to every line subscribed to the lane. Each line has a bounded
  outbox (`QUEUE_LIMIT = 256`, `messages.py:13`) where a keyed message replaces its queued predecessor in place
  (`Outbox.push`, `hub/core/line.py:32-45`); a full outbox closes the line with 4030 (`send`, `bus.py:40-42`). Lanes
  carry current state, never deltas (`bus.py:3-5`). A `beat` goes out after 25 s of silence (`Timing.beat_s`,
  `line.py:17`; `_write`, `bus.py:50-58`).
- Modules publish through `ModuleBus`, which prefixes both lane and type with `<id>.` unless already prefixed
  (`hub/core/context.py:55-68`).
- `presence()` (`bus.py:77-85`): `{screens: {role: count}, labels: {role: [labels]}, engines: vram.engines(), devices:
  {device id: open sockets}}`; republished on every connect, drop and device change (`presence_changed`, `:87-90`).
- Limits (`messages.py:8-14`, `:24-32`): frame ≤ 65 536 bytes (else close 1009), at most 16 lines (4013), rate 30/s
  with burst 60 (4029), 3 protocol strikes (4008), hello within 5 s (`Timing.hello_s`). Unpaired screens get 4003
  (`hub/core/runtime.py:138`).
- Sessions (`hub/core/session.py`): a session is open while at least one line is connected; a new random id each time
  one opens (`presence_changed`, `:20-29`). When the last line has been gone for the grace, 15 s
  (`Timing.session_grace_s`, `line.py:20`), `_end` (`:31-36`) calls `Core._session_ended`
  (`hub/core/runtime.py:106-109`): finished jobs are forgotten and the internal event `session.ended` is emitted. A
  window that reconnects within the grace keeps the session. "Nothing of a session is ever on disk" (`session.py:4`).

### 3.4 Jobs (`hub/core/jobs.py`, `dispatch.py`, `plan.py`)

- Memory only, lost on restart (`jobs.py:1`). States and transitions (`TRANSITIONS`, `:20-24`): queued → running |
  cancelled | failed (refused by the plan before it ran, `refuse`); running → running | done | failed |
  cancelled; terminal states have none. A job carries `notes` (what the Hub learned after submit: the plan, the
  judges' verdicts) on its card and in `job.finished` (`note`).
- One FIFO per lane (`queues`). `submit(kind, params, by="screen")` (`:67-95`): unknown kind → `Refused("not_found")`; the module's
  builder gets a deep copy of params and must return a `JobPlan` with tasks (`Invalid("params", "Nothing to run")`);
  no lane of `plan.lane_kind` → `Refused("unavailable", "Engine is offline")`; lane choice = a lane where the model is
  resident, else the shortest queue (`:80-82`); a queue at `queue.max_waiting` (default 10, `hub/settings.py:34`) →
  `Refused("queue_full")`. Job id `j_<10 hex>`; `tool` = the kind's module id. Emits `job.submitted` with `by`, who pressed (`:91-92`): `"screen"`
  for a web press (`job.submit` on the bus, `hub/core/routes.py:55`, and the Assistant's tools) or the module id for a job
  that module's `ctx.jobs.submit` made (`ModuleJobs.submit`, `context.py:77-78`, passes `by=self._id`). A listener uses it
  to tell its own press from another's (the Generate screen writes `last_seeds` only for its own or a screen's job; part 2).
- Dispatcher (`hub/core/dispatch.py`: `kick` `:57-64`, `_pump` `:70-80`, `_once` `:82-100`): one pump per lane, event-driven, head-of-line blocking by design. While its
  lane is offline or busy a job stays queued, and the lane's own change (Start, a job's end) kicks the
  pump again; otherwise the head job runs at once, or after its lane's other model is released (3.7).
- Publish rate (`publish`, `jobs.py:192-203`): state changes go out at once; progress-only updates at most every
  0.25 s per job (`PUBLISH_GAP_S`, `:25`), the newest replacing the queued one (key `job:<id>`).
- Terminal cleanup: the latest finished job per tool is kept (`terminal`); it is forgotten when another job of that
  tool finishes (`finish`, `:142-152`), when that tool's next job starts (`started`, `:135-140`), on `job.dismiss`
  (`:126-133`), or when the session ends (`forget_finished`, `:154-157`). A job that finishes while no session is
  open is forgotten at once (`:151-152`). Forgetting publishes `job.gone` (`_forget`, `:159-166`). `finish` emits
  `job.finished` with outputs (`:149`).
- Outputs: a lane `output` event whose item is a picture or a clip (`files.kind(item)` is not None) is appended to
  `job.outputs` and published on the `media` lane as `generation` with `kind` "image" or "clip"; a clip's `thumb` is
  None, its `w` and `h` come from the file (None when the event has none) and it carries `seconds`, its length (None
  unless a number; `_ev_output`, `dispatch.py:173-185`). An item of no known kind is dropped.
- Modules use `ctx.jobs`: a bare kind means `<own id>.<kind>` (`ModuleJobs.submit`, `context.py:77-78`).
- A task's `peak_vram_mb` less the lane's `baseline` (memory in use outside it at the job's start) is learned per model
  and GPU (`_ev_task_done`, `dispatch.py:187-193`; 3.7).

### 3.5 Engine (`ctx.engine`, `hub/core/enginequery.py:CatalogQueries.query`)

`ctx.engine` is the first engine lane, or `NoEngine`, whose `query` raises "No engine is set up on this server"
(`hub/core/context.py:48-52`; `hub/core/runtime.py:95`, `:112-115`). `EngineLane.query(what, **args)` is the mixin's
(`hub/core/enginequery.py:43-67`):

- `"models"` (`rescan=False`): the catalog plus `resident` (the loaded model). The catalog is kept in memory, then in
  `<data>/engine/catalog.json` under `catalog_key` (`hub/core/enginecat.py:29-43`: a SHA-256 over `shape:<SHAPE>`
  (`hub/worker/catalog.py:21`, 7 at this tree, bumped whenever the entry shape changes so an older cache is never served;
  `enginecat.py:32-33`), the engine python, root, args, model folders and the mtimes of `wgp.py`, `defaults`,
  `finetunes`, `ckpts`, the model folders and their first-level subfolders). `cached_catalog` (`:37-41`) answers from
  memory or that file and never starts the worker; the lane's profile check and the Settings view's video sizes use it.
  When the key has moved since the last query the memory copy is dropped (`:54-57`). On a miss the worker is started if
  needed, asked `query catalog`, and stopped again if it holds no model (`_load`, `:69-82`; single flight via
  `_fetching`; `_fetch_catalog`, `:84-96`, writes the cache). Each model gets `lora_extra` for the LoRA folders
  (`with_lora_roots`, `enginecat.py:62-69`).
- `"weights"` (`rescan`, `choose=(path, base)`): the Image models panel from `autoreg.panel`; `choose` saves the
  base chosen in `<data>/engine/choices.json` first (`hub/core/autoreg.py:247-265`; `enginequery.py:46-50`).
- `"files"` (`rescan`, `choose=(model, part, path)`): each catalog model's parts that name a file
  (`hub/worker/adapters/modelfiles.py` `parts`), asked beside a running job and kept while the catalog key stands;
  `choose` waits for the job lock, writes `finetunes/<id>.json` (or the Hub's pointer of that id) holding only the
  choices made and `hub_files` (what each part was), stops the worker and rescans (`_model_files`, `_choose_file`).
  The files chosen in Settings are claimed by real path (`definitions.weights` `claimed`), and a chosen text encoder gets no
  Text Encoder config choice (`upstream.encoders`).
- `autoreg.refresh` writes pointer definitions (`hub_auto`) into the engine's `finetunes` folder for weight files no
  definition names, matched by safetensors tensor names (Jaccard ≥ 0.9) and size ratio 0.25–1.3
  (`hub/core/autoreg.py:1-14`, `:28`); tensor names are cached in `<data>/engine/fingerprints.json`
  (`hub/core/fingerprints.py:33-64`). Weight files are never copied, moved, linked or deleted (`autoreg.py:14`). When a
  definition was written or removed, the engine is stopped, started again, asked again and stopped (`_reread`, `:98-109`),
  because it reads definitions only at start.
- The entries the worker builds, including the `kind` and `video` facts of a clip model, are described in part 5 (5.3.2).
- Settings edits call `lane.configure(engine, lora_folders, restart)`: engine path, model folder or memory profile changes
  stop the worker (after a running job) and drop the catalog (`hub/core/engine.py:129-141`; `hub/core/apply.py:17`,
  `:34-39`). A change to `profile_video` alone restarts nothing: `configure` only stores the settings (`engine.py:131`),
  and `_follow_profile` (`hub/core/enginelane.py:72-82`) compares the profile at the next job (1.5).

### 3.6 Devices and pairing (`hub/core/devices.py`, `guard.py`, `web.py`, `admin.py`)

- Registry `<data>/devices.json` (mode 0600), entries `{id: d_<8 hex>, name, addrs, key_hash}`; only
  `sha256:<hex>` of each device's 32-byte secret is stored (`:1-6`, `_hash`, `:28-29`).
- Codes: `mint_code(name)` writes `<data>/run/pair/<sha256(code)>` with `{name, expires}`; TTL 600 s
  (`CODE_TTL_S`, `:24`; `:130-136`). `redeem(code, addr)` (`:163-189`) deletes the file first (single use), checks
  expiry, creates or replaces the device by name (case-insensitive), sets `addrs=[addr]`, a new secret, and closes the
  device's open sockets.
- Admission (`Gate.admit`, `hub/core/guard.py:65-82`): mutating requests and all WebSockets need `Origin ==
  http://<Host>`; the cookie `hub_screen=<id>.<secret>` is verified and the device is accepted only from the
  addresses it paired from. Route classes (`:3-7`): `public` (shell pages; any paired device's address), `pair`
  (`/pair`, `/api/pair`, `/assets/*`; also loopback, or anyone while a code is open), `screen` (API, `/bus`, `/files`,
  `/thumbs`, uploads; cookie + address).
- `POST /api/pair` (`hub/core/web.py:47-62`): 5 failures in 60 s from one address block it for 600 s
  (`pair_failed`, `guard.py:92-100`); success sets the cookie `HttpOnly`, `SameSite=Strict`, max-age 34 560 000 s
  (`set_cookie`, `web.py:23-24`).
- `NetworkAdmin` (`hub/core/admin.py`) is the Network card's view: server addresses (read-only), devices with
  connection counts, pending codes, rename, remove (not the current device, not the last one, `devices.py:203-213`),
  pairing links, and `set_port` → `Core.change_port` (`hub/core/runtime.py:180-198`: 1024–65535, free on every bound
  address, saved, then a restart 1 s later).

### 3.7 VRAM / GPU (`hub/core/vram.py`, `plan.py`, `probes.py`)

A job never waits on memory other programs use (other programs may share the engine's GPU on purpose):
`plan.decide` either runs it, or, when the lane's worker holds a different model, releases that first and then
runs it (amber), and nothing names, lists or counts another program. NVML (`Probes.gpus`) is read only at decision
points (a job's start and end, a new screen, a lane change, `gpu.refresh`, boot) for the `gpu` snapshot `{read_at,
gpus: [{uuid, name, total_mb, used_mb, free_mb, lanes: [{id, kind, state, model}], unknown}]}` and for the per-model
peak table learned at runtime (`task_done.peak_vram_mb` less the memory in use outside the lane at the job's start,
last three per `model|gpu`, memory only), which picks the amber text ("Loading X" or "First run of this model"). The decision is
`plan.decide(Situation(lane, model, label, resident, need))` (`hub/core/plan.py:28-36`; `Situation` `:12-17`, `Plan(light,
action, text, release)` `:21-25`): a job whose model is `api.NO_MODEL` (`""`, `api.py:115`; the Stage 11 join) is green,
`run`, "Joining clips", and never releases anything (`plan.py:31-32`; `enginelane.py:62-63` and `dispatch.py:191` also
skip it, so nothing is loaded, freed or learned); otherwise a model in `resident` is green, `run`, "<label> loaded"; otherwise amber, and when
the lane holds another model the plan is `release` of that lane with "Switching to <label>", else `run` with "Loading
<label>", or "First run of this model" while no peak is learned. `Vram.plan` (`hub/core/vram.py:70-74`) builds the situation
from `lane.residency()` and the largest of the model's last three learned peaks (`need`, `:54-56`; `learn`, `:58-61`;
`baseline`, `:63-68`); the dispatcher's `_once` (`dispatch.py:82-100`) calls it, releases first when the plan says so
(`Vram.release`, `:134-145`), and starts the job. The lane also stops the worker itself before a job on a different model
and after every clip (1.5), so the plan's release rarely finds a worker still holding the other model.
The idle unload (`vram.idle_unload`, `vram.idle_minutes`) and `gpu.release` free the worker's memory; lane states are
`unloading, loading, busy, down, ready, idle`.

### 3.8 Internal events (`ctx.emit`, `Module.listens`)

`Events` (`hub/core/context.py:24-45`) delivers to module `listens` only, never to screens. `emit` deep-copies the
data per listener and runs each listener as its own task; listener exceptions are swallowed (`_call`, `:41-45`).
Events the core emits:

| Event | Data | Where |
|---|---|---|
| `job.submitted` | `{job, kind, tool, by, params}`; `by` is `"screen"` or the module id that submitted (3.4) | `hub/core/jobs.py:91-92` |
| `job.finished` | `{job, kind, tool, state, outputs}` | `hub/core/jobs.py:149-150` |
| `session.ended` | `{}` | `hub/core/runtime.py:109` |
| `settings.lora_folders` | `{folders}` | `hub/core/apply.py:18`, `:39-40` |

Modules may emit any name through `ctx.emit` (`context.py:109-110`); listeners are registered by event name in
`Core.load_modules` (`hub/core/runtime.py:129-130`).

## 4. HTTP and bus surface owned by the core

### 4.1 HTTP routes

All routes except `/mcp` are built by `http_route` (`hub/core/guard.py:129-152`): admission first, then the
content-type rule (mutating requests need `application/json`, or an image type where allowed, else 415), a body cap
(default 64 KiB), and error mapping (`error_response`, `:109-116`: `Invalid` → 400 `{code: "invalid", field, text}`,
`Refused` → status from `STATUS` (`:40`: invalid 400, forbidden 403, not_found 404, queue_full 409, rate 429,
unavailable 503), bad JSON → 400, anything else → 500). `None` → 204, dict/list → JSON.

| Method + path | Auth | Handler | Notes |
|---|---|---|---|
| `GET /`, `/media`, `/clips`, `/screen/{n}` (n 1–9) | public | `web.py:page` (`web.py:64`) | `web/dist/index.html`, `no-store`; placeholder text when the UI is not built |
| `GET /pair` | pair | `web.py:page` | |
| `GET /assets/{path}` | pair | `web.py:asset` | hashed assets, `immutable`, real-path contained in `dist/assets` |
| `POST /api/pair` | pair | `web.py:pair` | body cap 4 KiB, rate limit |
| `GET /files/{item}` | screen | `fileroutes.py:serve_file` | `existing_media` (a picture or a clip), `no-store`, 404 otherwise; a clip is `video/mp4` and `FileResponse` answers `Range` itself: 206 with `Content-Range`, 416 past the end (`:60-66`; pinned by `tests/core/test_clips_http.py:40`, which also shows a picture answers a range) |
| `GET /thumbs/{item}/{size}` | screen | `fileroutes.py:serve_thumb` | WebP from memory, rendered in the executor |
| `POST /api/upload` | screen | `fileroutes.py:upload` | PNG/JPEG/WebP ≤ 25 MB; magic bytes must match the content type; Pillow format must match; ≤ 64 MP; `verify()`; then `take_in` → `{id}` (`:31-56`, `:76-91`) |
| `POST /api/media/check` | screen | `fileroutes.py:check` | 1–50 ids, each `existing_image` → `{placed: [{item, id}]}` |
| `GET /api/settings` | screen | `routes.py:get_settings` | `Core.settings_view()` |
| `PATCH /api/settings` | screen | `routes.py:patch_settings` | `Core.update_settings(body)` then the view |
| `POST /api/settings/restart` | screen | `routes.py:restart` | marker + `systemctl --user restart hub.service` after 0.5 s |
| `GET /api/cards` | screen | `routes.py:get_cards` | `Core.cards()` |
| `GET/POST/DELETE /mcp` | own | `mcp.py:McpEndpoint.endpoint` | see 4.3 |
| `WS /bus` | screen | `bus.py:Bus.serve` | unpaired → accept + close 4003 |
| `/api/<module-id><path>` | per `Route.auth` | module | `body="any"` (JSON or image types), `Route.body_limit` |

`Core.settings_view()` (`hub/core/runtime.py:154-167`) returns `diagnostics`, `vram.{idle_unload, idle_minutes}`,
`version`, `started`, `data`, `drive`, `characters`, `engine.{root, python, ok, profile, profiles, profile_video,
video_profiles}` (the memory profile and its menu from `profile_choices`, `hub/settings.py:93-97`; the video models'
profile and its menu, which starts with "Same as above", from `video_profile_choices`, `:99-101`), `image_model_folders`,
`lora_folders`, `video_tiers` and `video_tiers_max`, and known GPUs `{name, total_mb}`. `video_tiers` is `{names, offered}`
(`Core._video_tiers`, `:169-178`): `names` are the tier names of the video models in the engine's catalog as last read
(`cached_catalog`, never a worker start), in catalog order without repeats, and `offered` is what the size menu shows from the
`video_tiers` setting (the first N names, or the setting's names the catalog has), else the first three
(`VIDEO_TIERS_MAX`) when that leaves none. `Core.cards()` (`:221-233`) calls each `Card.state(ctx)`; an
exception becomes `"Unavailable"`/`error`; sorted by `(order, module)`. Card orders in the shipped manifests: Generate
Image 880, Network 900, Assistant 920 (`hub/core/api.py:65`; `hub/modules/*/manifest.py`).

`Guard` (`hub/core/guard.py:177-208`) wraps everything: the `Host` header must be in `hosts(settings, port)`
(`hub/settings.py:250-256`: each bind with the port, `localhost:<port>` when 127.0.0.1 is bound, plus
`server.extra_hosts`), else 400 (HTTP) or close 1008 (WebSocket). Every response gets CSP `default-src 'self'` with
`frame-ancestors 'none'` and `form-action 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy:
no-referrer`, COOP/CORP `same-origin` (`:30-34`), and `Cache-Control: no-store` unless the route set one. No CORS
headers are sent (`:8-9`).

### 4.2 Bus messages

Envelope `{t, id?, re?, d?}`; `t` matches `^[a-z0-9_.]{1,64}$`; `id`/`re` match `^[A-Za-z0-9_-]{1,40}$`; `d` is an
object or null (`parse`, `hub/core/messages.py:50-67`). The bus's own `PROTO = 1` (`messages.py:8`, checked in
`hello`); the worker's wire is a separate protocol, `PROTO = 2` (1.x, Wire protocol).

Screen → hub:

| `t` | Roles | Handler | Effect |
|---|---|---|---|
| `hello` | any (first frame) | `Bus._hello` | `{proto, role, screen, label ≤ 40, subs?}` → `welcome` |
| `sub`, `unsub` | any | `Bus._sub/_unsub` | lane set changes |
| `focus` | workspace | `Bus._focus` | `{tool}` (a module with a tab, or null) → `focus` on lane `focus` |
| `sockets` | workspace | `Bus._declare` | `{tool, sockets[≤64], mode, primary}` checked against the module's `SocketGroup`s |
| `send` | any | `Delivery.send` | `{items[1..50], socket, tool?}` → `deliver` to the focused line, or `delivery` failed at once |
| `received` | target line | `Delivery.received` | `{placed, refused}` → `delivery` done |
| `job.submit` | workspace, media | `routes.py:submit` | `{tool, kind, params}` → `reply {job, state, position}` |
| `job.cancel`, `job.clear`, `job.dismiss` | workspace | `routes.py` | |
| `gpu.refresh` | any | `routes.py:gpu_refresh` | reading (max age 1 s) + `gpu` publish |
| `gpu.plan` | workspace | `routes.py:gpu_plan` | `{model}` → `reply {light, text}` |
| `gpu.release` | workspace, media | `routes.py:gpu_release` | `{lane?}`; no lane = every idle lane |
| `engine.start` | workspace | `routes.py:engine_start` | `reset()` on every lane |
| `<module-id>.<name>` | per module | `routes.py:module_call` (`bus.fallback`) | `fn(ctx, {screen, role, device}, d)` → `reply` |

(`install_handlers`, `hub/core/routes.py:42-125`; built-ins, `hub/core/bus.py:30-31`; delivery,
`hub/core/delivery.py:42`.)

Hub → screen: `welcome` (`{proto, boot, version, you, limits, tools, presence, focus}` plus `session, jobs, gpu,
settings, cards` from `Core._welcome`, `hub/core/runtime.py:244-248`), `reply`, `error {code, text, field?}`, `beat`,
`going_off {reason, back_in_s}`, `presence`, `focus`, `job`, `job.gone`, `gpu`, `generation` (lane `media`),
`settings` and `cards` (lane `settings`), `deliver`, `delivery`, and module types `<id>.<type>` on module lanes.
Error codes seen: `protocol`, `invalid`, `internal`, and `Refused` codes (`bus.py:208-215`). Delivery keeps each send
id and result for 10 minutes, at most 256, so a retried `send` is never delivered twice (`delivery.py:1-5`,
`:21-22`); a `deliver` unanswered in 5 s fails with `timeout` (`Timing.deliver_s`).

### 4.3 The MCP endpoint (`hub/core/mcp.py`)

- Transport subset (`:1-6`): `POST /mcp` only (GET/DELETE → 405 with `Allow: POST`), JSON-RPC 2.0, stateless (no
  session id), JSON replies only, notifications → 202, body ≤ 1 MiB (`BODY_LIMIT`, `:41`). Protocol versions
  `2025-11-25`, `2025-06-18`, `2025-03-26` (`VERSIONS`, `:37`); an unsupported `MCP-Protocol-Version` header → 400
  plain text. Methods: `initialize` (capabilities `{"tools": {"listChanged": false}}`, server name `hub`), `ping`,
  `tools/list`, `tools/call`; anything else → -32601 (`handle`, `:143-159`).
- Order of checks (`endpoint`, `:103-141`): a present `Origin` that is not `http://<Host>` → 403; the Assistant switch
  off → 503 "Assistant access is off" whatever key is sent; `Authorization: Bearer <key>` missing or wrong → 401;
  version header; content type `application/json` (else 415); JSON-RPC shape.
- The route is not built with `http_route`, so device cookies and paired addresses are not checked; the outer
  `Guard` Host check still applies. The endpoint URLs shown are one per bound address (`hub/core/runtime.py:89-91`).
- Access state (`McpAccess`, `:54-96`): `<data>/core/mcp.json` holds `{version, enabled, key}`; the key is
  `secrets.token_urlsafe(32)`, made on first start and on `rotate_key()`; compared with `hmac.compare_digest`
  (`key_ok`, `:69-71`). Retired keys `key_hash`, `max_proposals`, `proposal_ttl_min` are scrubbed (`:42`, `:50-51`).
  Recent clients (address, client name from `initialize`, time, status) are memory only, at most 8, shown for 600 s
  (`seen`, `clients`, `:77-87`). The Assistant module drives `set_enabled`/`rotate_key` through `ctx.mcp`.
- Tool calls (`call`, `:161-170`): `schema.check` then `tool.fn(ctx, args)`; the result is compact JSON text in
  `content[0].text`; `Invalid`/`Refused` → their text with `isError: true`; any other exception → "Something went
  wrong in the hub".

## 5. Settings

### 5.1 Structure (`hub/settings.py:DEFAULTS`, `:26-39`)

| Key | Default | Validation (`validate`, `:157-208`) |
|---|---|---|
| `version` | 2 | always rewritten to 2 |
| `server.bind` | `["127.0.0.1"]` | numeric IPs, no duplicates, `0.0.0.0`/`::` only with `allow_any_interface` (`check_bind`, `:141-154`) |
| `server.port` | 42010 | 1–65535 |
| `server.extra_hosts` | `[]` | lower-cased, `name:port` (`_HOST`, `:47`) |
| `server.allow_any_interface` | false | bool |
| `engine.python`, `engine.root` | `""` | strings |
| `engine.args`, `engine.model_folders` | `[]` | lists of strings |
| `engine.cc`, `engine.cxx` | `""` | full paths or empty: the C and C++ compilers the engine's kernels build with, written by `hub engine set` (the engine installer) and passed to the worker as `CC` and `CXX` (`supervisor.worker_env`); a change restarts the worker (`apply.ENGINE_KEYS`) |
| `engine.profile` | `"engine"` | `"engine"` (leave the engine config's own) or one of the engine's memory profiles 1, 2, 3, 3.5, 4, 4.5, 5 (`PROFILES`, `hub/settings.py:44-46`; `_profile`, `:82-91`; a whole number is kept whole); read by the worker at each engine start (5.2.1 and 5.2.8 in part 5) |
| `engine.profile_video` | `"same"` | `"same"` (follow `engine.profile`), `"engine"`, or one of the same profile numbers (`_profile` with the field name `engine.profile_video`, `:82-91`; `SAME`, `:43`). Used for a job on a video model: `supervisor.job_profile` (`hub/core/supervisor.py:67-71`); the lane checks it before every job and restarts the worker only when the arguments differ (1.5) |
| `paths.drive`, `paths.characters` | `""` | strings; empty = not chosen |
| `gpus` | `[]` | each `{id ^[a-z0-9_]{1,20}$ unique, index 0–63, uuid str/null, engine bool}`, no other keys (`_gpus`, `:211-229`) |
| `vram.idle_unload` | true | bool |
| `vram.idle_minutes` | 10 | 5–120 |
| `queue.max_waiting` | 10 | 1–100 |
| `diagnostics` | false | bool |
| `modules_disabled` | `["storyboard"]` (`hub/settings.py:39`) | list of strings (`_strs`, `:198`); `registry.discover` skips these module ids (`hub/server.py:96`). The storyboard module is listed by default, so the tool server serves its six tools and none of the storyboard module's eight until the name is removed from the list |
| `paths.storyboards` | absent | optional (`OPTIONAL`, `:126`): left out of the file until storyboards are turned on in Settings, `STORYBOARDS` = `"Storyboards"` (`:127`) is the name it then takes by default; a folder inside the Drive (`_inside_drive`, `:67-75`, applied at `:182-183`), read by `storyboards_folder` (`:271-273`) and given to `Files.set_storyboards` at start (`runtime.py:83`) and on a settings change (`apply.py:32-33`). It is not in the Settings screen's editable list |
| `modules` | `{"generate-image": {"ref_caps": {"qwen_image_21": 6, "krea2_": 2}, "video_tiers": ["540p", "720p"], "continue_max_seconds": 60}, "storyboard": {"cell_text_max": 4000, "max_cells": 24}}` (`:40-42`) | each value an object; module defaults merged under the saved values (`:198-199`); `ref_caps` values 1–6 (`:200-203`) |
| `modules.generate-image.video_tiers` | `["540p", "720p"]` | a whole number 1–3 (how many of the catalog's first video size tiers the size menu offers), or a list of 1–3 different tier names matching `^[A-Za-z0-9_.\-]{1,16}$` (`_tiers`, `:104-114`, applied at `:204`; `VIDEO_TIERS_MAX` = 3, `:50`); names the catalog does not report are ignored where they are used (`models.offered_tiers`, `hub/modules/generate_image/models.py:53-60`) |
| `modules.storyboard.cell_text_max`, `modules.storyboard.max_cells` | 4000, 24 | whole numbers: the text of a cell, 1 to `pngtext.MAX` (16 384, imported as `TEXT_CEILING`, `:15`), and the cells of a storyboard, 1 to 99 (two-digit names) (`:211-213`). Read by the storyboard module (part 4, 4.9); not editable from the Settings screen |
| `modules.generate-image.continue_max_seconds` | 60 | a whole number 10–600 (`_int`, applied at `:205-206`): the longest scene a continued clip may grow to. The engine decodes the whole source and holds the joined file in RAM, so the scene's length bounds a continue's memory (`settings.py:9-11`). Read by the generate-image module's `continue` route (part 2, 2.10.7); not editable from the Settings screen |

Unknown keys raise `SettingsError("<field>", "unknown setting")` (`_merge`, `:130-139`); the retired keys
the keys an older hub wrote and this one no longer has (`RETIRED`, `:127`: `vram.ram_reserve_mb`, `paths.outputs`, `paths.inputs`,
`paths.archive` and two more) are dropped when read, so a `settings.json` an older hub wrote still loads (`tests/core/test_settings_retired.py`).
LoRA folders live at `modules.loras.folders` (written by `hub init`, `hub/__main__.py:145-147`; edited through
`ui_patch`). Temp is never a setting: it is always `<data>/outputs` (`drive_root` docstring, `:258-261`).
`load` (`:231-240`) reads `<data>/settings.json`; `save` (`:242-244`) validates and writes atomically (0600).

### 5.2 Edits from a screen (`ui_patch`, `hub/settings_edit.py:17-42`; `pathrules`)

The edit lives in `hub/settings_edit.py` (the schema and defaults stay in `hub/settings.py`). Editable here (`_EDITABLE`,
`settings_edit.py:11-13`): `vram.idle_unload`, `vram.idle_minutes`, `paths.drive`, `paths.characters`, `engine.root`,
`engine.python`, `engine.model_folders`, `engine.profile`, `engine.profile_video`, `modules.loras.folders`, and
`diagnostics`; and one setting of a module (`_MODULE_EDITABLE`, `:14`): `modules.generate-image.video_tiers`. `paths.storyboards` and `modules.generate-image.continue_max_seconds` are not on the list: they are changed in `settings.json`. Anything
else is refused with one line (`:22-23`, `:27-28`, `:35-36`). The result is checked again by `settings.validate`
(`:42`). `apply` treats `engine.profile` like the other engine keys (`ENGINE_KEYS`, `hub/core/apply.py:17`): the lane's
`configure` rebuilds the worker arguments (`--profile`), stops the worker after a running job and drops the catalog, so
the next start reads the new profile (`tests/engine/test_memory_profile.py:63`). A job on a video model takes `profile_video` unless it is `same`, and the worker restarts only when that differs from the running one (`hub/core/enginelane.py:72-82`). `engine.profile_video` is not in
`ENGINE_KEYS` (`apply.py:18` says why): `configure` stores the new settings (`engine.py:131`) and the lane compares the
profile at the next job, so changing it alone restarts nothing until a video model is run with a different profile
than the running worker has. Bind addresses change only through `hub network` (`hub/core/admin.py:3-5`).

`pathrules` (`hub/pathrules.py`) checks, never creates or writes (`:1-4`):
- `_absolute` (`:19-26`): non-empty string, no NUL, absolute; normalised.
- `folder` (`:29-39`): exists, is a directory, readable (+ writable when `write=True`).
- `folders` (`:42-51`): a list of at most 32 (`MAX_FOLDERS`), each a readable folder, no duplicates.
- `engine_root` (`:54-58`): a folder containing `wgp.py`. `python` (`:61-67`): an executable file.
- `drive_root` (`:76-89`): a writable folder, not overlapping the Hub's own data folder, the engine root, a model folder
  or a LoRA folder (`overlaps` compares real paths, `:70-73`).
- `_check_paths` (`hub/settings_edit.py:48-78`): Characters may be set back to `""`; edited engine root, model folders and
  LoRA folders may not overlap Temp, the Drive or Characters.

`Core.update_settings` (`hub/core/runtime.py:206-219`): `ui_patch` → `save` → `apply(core, old)` (repoint media roots,
`configure` lanes, refresh module ctx settings, emit `settings.lora_folders`) → publish `settings` → `vram.rearm()` →
cards. `apply` does not read `diagnostics`; the worker's output passthrough is fixed when the lane is created
(`hub/core/engine.py:222-223`).

### 5.3 On disk vs memory

On disk under `<data>` (the unit sets `UMask=0077`; `write_json` uses 0600):

| Path | Writer |
|---|---|
| `settings.json` | `hub/settings.py:save` |
| `devices.json`, `run/pair/<sha256>` | `hub/core/devices.py` |
| `run/restart` (marker), `run/worker-<gpu>.pid` | `hub/__main__.py:_restart`, `Core.restart`, `Supervisor._write_pidfile` |
| `core/mcp.json` | `McpAccess` via `JsonDoc` |
| `outputs/<day>/...` (Temp) | `Files.take_in`, `enginecat.land`; `temp.regroup` makes `outputs/<day>/<group>/` (Favorites) |
| `clips/<day>/<time>.mp4` | `enginecat.land` (flat in the day folder), `temp.file_clip` (the storyboard skeleton only) |
| `engine/catalog.json`, `engine/fingerprints.json` (0644), `engine/choices.json` | `enginecat.write_cache`, `fingerprints.write_json`, `autoreg` |
| `engine/<gpu>/config/wgp_config.json`, `outbox/`, `settings/`, `config/ckpts` (scratch) | worker (`wan2gp.seed_config`, `Engine.open`) |
| `engine-home/` | worker `HOME` (`supervisor.py:63`) |
| `clips/sequences/<name>.json` | `hub/core/sequences.py` (through `Files.sequence_new`, `sequence_save`, `sequence_rename`, `sequence_delete`; one file per sequence, written with `store.write_json`; clip ids, order and in and out points only) |
| `<module-id>/<name>.json` | module `ctx.doc` |

Memory only: jobs and queues (`jobs.py:1`), the session (`session.py:4`), thumbnails (`thumbs.py:1-4`), learned VRAM
needs (`vram.py:58-61`), MCP recent clients (`mcp.py:46`), delivery records (`delivery.py:1-5`), bus lines and focus.

Outside `<data>`: pictures in the Drive and Characters folders (set in Settings), and pointer definitions marked
`hub_auto` in `<engine root>/finetunes/` (`hub/core/autoreg.py:7-14`; `hub/worker/wan2gp.py:3-4`).

### 5.4 Owner's hard rules as the code enforces them

| Rule | Enforcement |
|---|---|
| Nothing fetched from the internet | Controller: `netlock` audit hook installed first in the CLI; it refuses `connect/sendto/sendmsg` to non-loopback, non-Unix addresses and non-numeric name lookups, and cannot be removed (`hub/core/netlock.py:1-6`, `:43-65`; `hub/__main__.py:5-7`). Worker: `netguard` (same rules) and `OFFLINE_ENV` (`HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`). Tests ban HTTP client imports in `hub/` (`tests/core/test_rules.py:16-18`, `:37-40`). The Assistant's Open WebUI link accepts only a numeric loopback address (`hub/modules/assistant/link.py:37-49`). Front end: CSP `default-src 'self'`; no absolute URLs in source and no external URLs in the build (`web/tests/unit/guards.test.ts:63-69`, `:83-92`). |
| No telemetry | `OFFLINE_ENV`: `HF_HUB_DISABLE_TELEMETRY=1`, `DO_NOT_TRACK=1`, `GRADIO_ANALYTICS_ENABLED=False` (`hub/worker/protocol.py:28-38`); engine plugins, services and notifications dropped from its config (`wgpconfig.py:17`, `:73-75`); the network hooks above. |
| No logs | uvicorn `access_log=False`, `log_config=None`, `log_level="error"` (`hub/server.py:42-47`); stdout is two lines per run (`hub/server.py:1-3`, tested in `tests/core/test_process.py`); worker stdout/stderr go to `/dev/null` unless Diagnostics (`supervisor.py:168`); engine code may not import `logging` or call `print(` except `print(one_line` (`tests/engine/test_rules.py:31-35`); front end: no `console.` (`guards.test.ts:63-69`); no queue file written after an engine error (`save_queue_if_crash=0`, `wgpconfig.py:18-20`; queue zips deleted, `wan2gp.py:133-136`). |
| No metadata in pictures, except character notes | `clean.strip` on every upload, every engine picture and every named picture put in (`files.py:169`, `enginecat.py:147`, `named.py:153`); `clip.strip` on every engine clip (`enginecat.py:132`; 1.5), with the engine's MP4 container forced (`video_container="mp4"`, `wgpconfig.py:20`); engine forced to `metadata_type="none"`, PNG, `embed_source_images=False` (`wgpconfig.py:18-20`); Temp and clip names are the time only (`files.py:35-46`); thumbnails in memory, served `no-store` (`thumbs.py`, `fileroutes.py:65`, `:74`); older on-disk records erased at start (`files.py:50-64`). The one exception is the `Description` iTXt chunk, written by `pngtext.py` alone (`:19-50`; a guard test walks `hub/`), in a character PNG and, once `paths.storyboards` is set, in a picture one level under that folder (`named.text_allowed`, `named.py:79-99`). |
| No credentials beyond the configured keys | Device secrets are stored only as SHA-256 (`devices.py:3-4`, `:28-29`); the MCP key is generated locally and compared in constant time (`mcp.py:52-53`, `:69-71`); the engine config copy drops `services`/`llm_engines` (`wgpconfig.py:17`, `:73-75`); a test rejects long hex/base64 string literals in `hub/` (`tests/core/test_rules.py:43-54`). The Open WebUI API key typed on the server's card is kept by the Assistant module in `<data>/assistant/openwebui.json` (`hub/modules/assistant/chat.py:74`). |

## 6. Repository rules enforced by tests

| Rule | Guard | Location |
|---|---|---|
| Python files ≤ 300 lines; files over 3 lines start with `from __future__ import annotations` | `test_files_stay_small_and_typed` | `tests/core/test_rules.py:73-79` |
| No HTTP client imports (`httpx`, `requests`, `urllib.request`, `http.client`, websockets clients, …) | `test_no_http_client_imports` | `tests/core/test_rules.py:16-18`, `:37-40` |
| No literal secrets (32+ hex, or mixed-case 32+ base64-url) | `test_no_literal_secrets` | `tests/core/test_rules.py:43-54` |
| Modules import only the API; core never imports modules | `test_modules_import_only_the_api`, `test_core_never_imports_modules` | `tests/core/test_rules.py:57-70` |
| Installed controller packages equal `requirements/controller.lock` | `test_installed_packages_match_the_lock_exactly` (skipped if no lock) | `tests/core/test_rules.py:82-104` |
| Engine code: no content-filter words (the test holds the list), no `logging`, no `print(` | `test_no_content_filters_and_no_logging` | `tests/engine/test_rules.py:31-35` |
| Worker is stdlib only | `test_worker_is_stdlib_only` | `tests/engine/test_rules.py:38-46` |
| No engine key family in any `hub/**` file outside `hub/worker/adapters/` | `test_no_engine_key_family_outside_the_adapters` | `tests/engine/test_rules.py:59-69` |
| Front-end source and test files ≤ 250 lines | `guards` | `web/tests/unit/guards.test.ts:22-25` |
| `overflow: hidden` banned; only `[data-scroll]` in `base.css` scrolls; `html, body, #root, .app` use `overflow: clip` | `guards` | `web/tests/unit/guards.test.ts:27-38` |
| No `px` except 1px/0px hairlines and the one root clamp `--ui-base`; no px font sizes, no inline `fontSize` | `guards` | `web/tests/unit/guards.test.ts:19`, `:40-53` |
| Banned UI copy (explanatory/safety/directive phrases) | `guards` | `web/tests/unit/guards.test.ts:55-61` |
| No `console.`, `localStorage`/`sessionStorage`, or absolute URLs in front-end source | `guards` | `web/tests/unit/guards.test.ts:63-69` |
| Ruff line length 120, rules `E, F, W, I, B, UP`, target py313 | configuration only | `pyproject.toml` `[tool.ruff]` |
## 7. Where a thing lives

| Concept | File | Function / symbol |
|---|---|---|
| CLI entry, command parsing | `hub/__main__.py` | `main`, `_parser` |
| Network seatbelt (controller) | `hub/core/netlock.py` | `install`, `_hook` |
| First settings / LAN address | `hub/__main__.py` | `cmd_init`, `cmd_network`, `lan_address` |
| Pairing link on the terminal | `hub/__main__.py` | `main` (`pair`) → `Devices.mint_code` |
| Server start, sockets, uvicorn config | `hub/server.py` | `serve`, `bind`, `config`, `build` |
| Shutdown / restart marker | `hub/server.py`, `hub/core/runtime.py` | `HubServer.shutdown`, `Core.stop`, `Core.restart` |
| Service assembly, ASGI app | `hub/core/runtime.py` | `Core.__init__`, `Core.app` |
| Module loading into services | `hub/core/runtime.py` | `Core.load_modules` |
| Module contract | `hub/core/api.py` | `Module`, `Ctx`, … |
| Module discovery and rules | `hub/core/registry.py` | `discover`, `validate` |
| MCP tool generation | `hub/core/features.py` | `tools_of`, `value_schema`, `lora_schema` |
| MCP argument checking | `hub/core/schema.py` | `check` |
| MCP endpoint and access switch | `hub/core/mcp.py` | `McpEndpoint.endpoint`, `McpAccess` |
| Module ctx, events | `hub/core/context.py` | `ModuleCtx`, `Events`, `ModuleBus`, `ModuleJobs` |
| JSON documents | `hub/core/store.py` | `JsonDoc`, `Store`, `write_json` |
| Item ids, roots (`out`, `clips`, `drive`, `chars`), uploads in | `hub/core/files.py` | `Files.resolve`, `existing_image`, `existing_media`, `kind`, `take_in`, `temp_path` |
| MP4 tags cut and facts read where a clip lands | `hub/core/clip.py` | `strip`, `facts`, `_strip`, `_children`, `_offsets` |
| Delete / move | `hub/core/files.py` | `Files.delete`, `move` |
| Groups in Temp, filing a clip, the newest Temp picture | `hub/core/temp.py` | `regroup`, `file_clip`, `newest_temp` (through `Files.regroup`, `file_clip`, `newest_temp`) |
| Drive folders | `hub/core/drive.py` | `listing`, `make`, `rename`, `move`, `remove` |
| Characters and notes | `hub/core/characters.py` | `listing`, `find`, `put`, `rename`, `remove`, `set_notes` |
| Named pictures (put, rename, text) in Characters and a storyboards folder | `hub/core/named.py` | `put`, `rename`, `text_allowed`, `read_text`, `write_text`, `set_text`, `folder_of`, `own` |
| Metadata stripping | `hub/core/clean.py` | `strip` |
| Thumbnails | `hub/core/thumbs.py`, `hub/core/files.py` | `ThumbStore`, `render`, `Files.thumbnail` |
| Media HTTP routes | `hub/core/fileroutes.py` | `file_routes`, `check_image` |
| Host check, headers, admission | `hub/core/guard.py` | `Guard`, `Gate.admit`, `http_route`, `ws_route` |
| Shell pages, pairing endpoint | `hub/core/web.py` | `web_routes` |
| Devices and pairing codes | `hub/core/devices.py` | `Devices.redeem`, `verify`, `mint_code` |
| Network card data | `hub/core/admin.py` | `NetworkAdmin` |
| Bus lines, lanes, presence, focus | `hub/core/bus.py` | `Bus.serve`, `publish`, `presence` |
| Outbox, rate bucket, timings | `hub/core/line.py` | `Outbox`, `Bucket`, `Timing` |
| Envelope, limits, close codes | `hub/core/messages.py` | `parse`, constants |
| Session and its 15 s grace | `hub/core/session.py` | `Session` |
| Core bus handlers, `/api/settings`, `/api/cards` | `hub/core/routes.py` | `install_handlers`, `core_routes` |
| Delivery (send → deliver → delivery) | `hub/core/delivery.py` | `Delivery` |
| Job book | `hub/core/jobs.py` | `JobBook.submit` (with `by`), `finish`, `publish` |
| Dispatch | `hub/core/dispatch.py` | `Dispatcher._once`, `_run` |
| VRAM decision (run, or release then run) | `hub/core/plan.py` | `decide`, `Situation`, `Plan` |
| VRAM readings, learned peaks, idle unload | `hub/core/vram.py` | `Vram.read`, `plan`, `need`, `learn`, `baseline`, `arm_idle` |
| NVML (the GPU reading) | `hub/core/probes.py` | `Probes.gpus` |
| Engine lane | `hub/core/engine.py` | `EngineLane`, `create`, `run`, `_task` |
| What the worker holds between jobs; release before a model switch and after a clip | `hub/core/enginelane.py` | `LaneMemory.held`, `_before`, `_after`, `_unload`, `_follow_profile`, `_kind` |
| `ctx.engine` queries, catalog fetch | `hub/core/enginequery.py` | `CatalogQueries.query`, `cached_catalog`, `_load`, `_fetch_catalog` |
| Catalog cache, landing outputs | `hub/core/enginecat.py` | `catalog_key`, `land` (returns `kind`), `progress`, `sweep` |
| Picture text field | `hub/core/pngtext.py` | `read`, `write` |
| Plain-value checks and clip planning a module shares | `hub/core/checks.py`, `hub/core/clipplan.py` | `whole`, `number`, `seed_value`, `seeds`; `clip_facts`, `snap_frames`, `frames_for`, `tier_size` (re-exported by `hub/core/api.py`) |
| Weight-file auto registration | `hub/core/autoreg.py`, `hub/core/fingerprints.py` | `refresh`, `panel`, `choose`, `Fingerprints` |
| Worker spawn / watch / stop | `hub/core/supervisor.py` | `Supervisor`, `make_spawn`, `worker_env` |
| Worker wire format, offline env | `hub/worker/protocol.py` | `OFFLINE_ENV`, `encode`, `decode` |
| Worker seatbelt | `hub/worker/netguard.py` | `install`, `_hook` |
| Worker entry | `hub/worker/main.py` | `main`, `serve`, `die_with_parent`, `dump`, `dump_engine` |
| Engine facts for the contract (`--dump-engine`) | `hub/worker/enginedump.py` | `build`, `redact`, `sterile`, `write` |
| Continue measurement (`--probe-continue`) | `hub/worker/probe.py` | `run`, `step`, `continue_task` |
| Forced engine config, profile keys, config seeding | `hub/worker/wgpconfig.py` | `FORCED_CONFIG`, `PROFILE_KEYS`, `seed_config`, `search_paths` |
| Forced task values and `translate`, per engine line | `hub/worker/adapters/fork.py`, `upstream.py` | `FORCED_TASK`, `FORCED_VIDEO`, `translate`, `factory_settings`, `lora_root`, `lora_search`, `probe` |
| The Hub's side of the engine seam: types, key families, `select`, `wire`/`parse` | `hub/worker/engineapi.py` | `ModelFacts`, `ClipRequest`, `KeyFamilies`, `Adapter`, `select` |
| The session loop, the clip guard | `hub/worker/wan2gp.py` | `Engine.open`, `_params`, `run`, `Peaks` |
| Memory profile choices | `hub/settings.py` | `PROFILES`, `profile_choices`, `video_profile_choices`, `ENGINE_OWN`, `SAME` |
| Memory profile for a job's model kind | `hub/core/supervisor.py`, `hub/core/enginelane.py` | `job_profile`, `worker_args`, `LaneMemory._follow_profile` |
| Engine failure text | `hub/worker/faults.py` | `failure` |
| Settings schema and validation | `hub/settings.py` | `DEFAULTS`, `validate`, `_tiers`, `RETIRED`, `OPTIONAL`, `storyboards_folder` |
| Settings screen's edit | `hub/settings_edit.py` | `ui_patch`, `_check_paths` |
| Path checks for edits | `hub/pathrules.py` | `folder`, `drive_root`, `overlaps` |
| Live apply of edits | `hub/core/apply.py` | `apply` |
| Version | `hub/__init__.py` | `VERSION = "0.1.0"` |
| systemd unit | `deploy/hub.service` | `ExecStart`, `OOMPolicy` |

## Gaps / unverified

- The brief names `hub/main.py`, `hub/runtime.py` and `app.py`; none exist at this commit. Their roles are covered by
  `hub/__main__.py`, `hub/server.py` and `hub/core/runtime.py`.
- Ruff line length 120 is configuration in `pyproject.toml`; no test or tool in the repository runs ruff. `tools/release.py`
  lists ruff as a dev package only.
- "No telemetry" and "no credentials beyond the configured API keys" are not enforced by one dedicated check; section 5.4
  lists the pieces of code that bear on them. The absence of telemetry code in `hub/` was not proven beyond the
  network hooks and the banned-import test.
- `netguard` and `netlock` are audit hooks; native code (e.g. CUDA or C extensions inside the engine) can bypass them,
  as `hub/worker/netguard.py:3-4` states. The OS firewall mentioned in `hub/core/netlock.py:5` is not part of this
  repository's Python code (the installer scripts in `install/` were not read).
- `FORCED_TASK.output_filename = "{date}-{seed}"` puts the seed into the engine's own outbox file name; the file is
  renamed to a time-only name when it lands in Temp or the clips root (`enginecat.land`). Whether the seed reaches any other place was
  not traced.
- `/mcp` does not check device cookies or paired addresses; access depends on the Host allow-list, the switch and the
  key. Whether that is the intended exposure on every bound address is stated in a code comment
  (`hub/core/runtime.py:89-90`) but not in a test name read here.
- `<data>/engine/definitions` is referenced by `autoreg.refresh` (`hub/core/autoreg.py:233`, `old = data /
  "definitions"`); its handling was not read in detail.
- `clip.strip` (`hub/core/clip.py`) has been run only on the synthetic MP4s of `tests/fakes/mp4.py`; Stage 0's results
  (the real codec, tags, size and time of an engine clip) are not written down. Which boxes a real
  engine file carries beyond `udta` and `moov/meta` is therefore unmeasured, and the walk leaves `mvhd`, `tkhd`, `mdhd`
  and `hdlr` as they are (`clip.py` and `engine.profile_video` are in the tree).
- `continue_max_seconds` defaults to 60 (`hub/settings.py:38`). The probe that measures a continue's memory on the real engine (`--probe-continue`, `hub/worker/probe.py`) is in the tree; no measured result of it is recorded in the documents read, so 60 s is a default, not a measured limit.
- `GONE` ("That image is no longer available", `hub/core/files.py:29`) is also what a missing clip says. `/files` sends
  `cache-control: no-store` for clips as for pictures, so a browser re-reads a clip on every seek (`fileroutes.py:66`).
- `hub/core/supervisor.py` imports `ENGINE_OWN` and `SAME` from `hub/settings.py` (`:23`): the core reads the settings module's
  constant, as `runtime.py` already read its functions.
- Module-side behaviour (which modules declare which screens, listings, actions, lanes and handlers) is out of scope
  and was only sampled.
