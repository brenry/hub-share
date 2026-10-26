# 4. The Assistant and the MCP tool server

Scope: everything about the assistant outside the direct scope of the Media and Generate Image modules.
That covers the `assistant` module (`hub/modules/assistant/*`), the core MCP endpoint and tool generation
(`hub/core/mcp.py`, `hub/core/features.py`, `hub/core/schema.py`, `hub/core/registry.py`), the `network`
module, core pairing (`hub/core/devices.py`, `hub/core/web.py`), and the web plumbing that carries them
(`web/src/lib/**`, `web/src/shell/**`, `web/src/screens/pair/*`, `web/src/modules/assistant/Card.tsx`,
`web/src/modules/network/*`), and, in 4.9, the declarations of the `storyboard` module (`hub/modules/storyboard/*`), which
publishes tools and nothing else.

Every statement below points at a file and line (`path:line`) or a function. Code in Open WebUI itself is not in
this repository. Where this section describes Open WebUI's behaviour, it repeats what the Hub's own docstrings
say about it and marks it as such.

---

## 4.1 The two directions of the link

The Hub and Open WebUI (0.11.4, run in Docker on the same host) call each other in both directions:

| Direction | Who calls | Endpoint | Auth | Code |
|---|---|---|---|---|
| (a) chat | Hub → Open WebUI | `POST /api/chat/completions` and `/api/v1/chats/*` | Open WebUI API key as `Authorization: Bearer` | `hub/modules/assistant/link.py` |
| (b) tools | Open WebUI → Hub | `POST /mcp` | Hub MCP key as `Authorization: Bearer` | `hub/core/mcp.py` |

### 4.1.1 (a) The Hub's line to Open WebUI (`link.py`)

- `link.py` speaks plain HTTP/1.1 over a raw asyncio socket. It sends one request per connection with
  `Connection: close` (`link.py:153` `_request`, `link.py:139` `_exchange`). Interim 1xx answers are skipped
  (`_exchange`).
- Every request carries `Authorization: Bearer <key>` and `Content-Type: application/json` (`_request`). For an
  IPv6 address the Host header is bracketed (`_request`, tested by `test_assistant_link.py:173`).
- Open WebUI must be on a **numeric loopback address**. `endpoint()` (`link.py:37`) accepts only `http://`, refuses
  a path, query, fragment or `@`, refuses a name ("Use 127.0.0.1, not a name"), refuses a non-loopback IP
  ("Open WebUI must be on this computer: use 127.0.0.1"), and refuses port 0.
- Limits: a completion may take `TIMEOUT_S = 600.0` s (`link.py:17`). Listing and deleting chats use
  `FORGET_S = 30.0` (`link.py:18`). A body is capped at `MAX_REPLY = 4 << 20` bytes (`link.py:19`). The header
  count is capped at `MAX_HEADERS = 100` (`link.py:20`).
- Every failure becomes one plain sentence raised as `Invalid` (`call`, `link.py:160`): a timeout gives `SLOW`, a
  refused connection gives `REFUSED`, a broken connection gives `STOPPED`, and an unreadable answer gives `UNREADABLE`.
  The texts are at `link.py:21-30`.
- `answer()` (`link.py:187`) maps 401/403 to `KEY_REFUSED` ("Open WebUI refused the key (Settings -> Account -> API
  keys)"). Any other non-200 status gives Open WebUI's `detail` string (cut to 300 chars, `_detail` `link.py:178`)
  or "Open WebUI answered HTTP N".

The calls that `link.py` makes:

| Function | Request | Use |
|---|---|---|
| `ask` (`link.py:199`) | `POST /api/chat/completions` `{model, messages, stream: false, **extra}` | plain mode; returns `choices[0].message.content` or `NO_TEXT` |
| `models` (`link.py:213`) | `GET /api/models` | model list; also proves the address and key |
| `tool_servers` (`link.py:222`) | `GET /api/v1/configs/tool_servers` | MCP tool servers (`type == "mcp"`, `info.id` non-empty) as `[{id, name}]`; a 401 whose detail starts with `PROHIBITED` → `NOT_ADMIN` |
| `new_chat` (`link.py:247`) | `POST /api/v1/chats/new` `{chat: {title: "Hub", models: [model], history: {messages: {}, currentId: null}, messages: []}}` | the conversation's Open WebUI chat; returns its `id` |
| `complete` (`link.py:258`) | `POST /api/chat/completions` (body given by caller), read with `keep=False` | tool-server turn; 404 → `GONE` |
| `saved` (`link.py:268`) | `GET /api/v1/chats/<id>` | reads `chat.history.messages[<message_id>]`; 401/404 whose detail is not one of `KEY_REFUSALS` → `GONE` |
| `remote.leftovers` (`remote.py:23`) | `GET /api/v1/chats/` | list for the sweep |
| `remote.delete` (`remote.py:39`) | `DELETE /api/v1/chats/<id>` | 200 or 404 = gone; anything else = Open WebUI's reason |

**Plain mode** is used when the "Tool server" setting is empty. `Chat.reply` (`chat.py:177-180`) calls
`link.ask(host, port, key, model, self.wire(), settings.params(c))` and adds the returned text as an `assistant`
message with `seconds`.

**Tool-server mode** is used when "Tool server" is set (`chat.py:181-208`). The module docstring
(`chat.py:8-16`) gives the reason: Open WebUI runs tools only for a reply that is saved in one of its chats. The
Hub therefore makes one Open WebUI chat per conversation, sends each completion into it with `stream: true`, waits
until Open WebUI has finished its whole loop, and then reads the saved reply. The saved message's `output` items
(Open WebUI's `function_call` / `function_call_output` / `message` items) are kept in memory on the Hub's
`assistant` message and sent back with the next turn. The docstring states that Open WebUI turns them back into
the model's tool calls (`utils/middleware.py process_messages_with_output`, cited at `chat.py:15-16`).

### 4.1.2 (b) Open WebUI → the Hub's MCP endpoint

- The Hub is registered as an MCP tool server in Open WebUI (Admin → External Tools, Auth: Bearer, the Hub's
  MCP key). The instruction text is shown on the Assistant card (`web/src/modules/assistant/Card.tsx:149`).
- The Hub lists Open WebUI's MCP tool servers through `link.tool_servers`. One is picked on the server's card, and its
  `info.id` is saved as the `tools` setting (`Card.tsx:50-53`, `settings.py`).
- Each tool-server completion carries `tool_ids: ["server:mcp:<tools>"]` (`chat.py:190`). The test fixture
  registers the Hub's server with `info.id = "hub"`, so the request carries `"server:mcp:hub"`
  (`tests/fakes/openwebui.py:136-138`, `tests/core/test_assistant_tools.py:40-42`).
- The `hub/core/mcp.py` docstring (`mcp.py:8-14`) records how Open WebUI 0.11.4 sends the key. It builds
  `Authorization: Bearer <key>` for auth_type "bearer" and passes it to the MCP client's httpx default headers.
  The key therefore goes on every POST, `initialize` included. The docstring cites Open WebUI source lines, which
  are not verifiable in this repo.
- The endpoint answers on every address the hub binds. The runtime comment (`hub/core/runtime.py:89-91`) explains
  why: Open WebUI in a container calls from the Docker bridge, not from 127.0.0.1. `mcp.endpoints` lists one URL
  per bound address.

### 4.1.3 Sequence of one tool-server turn

1. The window posts `POST /api/assistant/chat {"text": ...}` (`web/src/modules/generate-image/chat/assistant.ts:28-36`
   `say`). `routes.chat_send` (`routes.py:82`) refuses empty text with "Write a message". It answers
   `409 {"code":"busy"}` while a turn runs. Otherwise it calls `Chat.send` and answers `202 {"turn": <id>}`.
2. `Chat.send` (`chat.py:131`) sets `busy = True`, appends the `user` message (which publishes `assistant.chat`) and
   starts `Chat.turn` as a task.
3. `Chat.reply` (`chat.py:170`) reads the settings. With no model it raises "Set the Open WebUI model name in
   Settings -> Assistant" (`chat.py:174-175`). It resolves `link.endpoint(url)`.
4. With `tools` set, it checks `ctx.mcp.state()["on"]`. If access is off it raises `ACCESS_OFF` ("Assistant access
   is off, so Open WebUI cannot reach the Hub tools", `chat.py:52`, `chat.py:181-182`). No request goes to Open
   WebUI (`test_assistant_tools.py:139-156`).
5. Under `self.lock`, if there is no Open WebUI chat yet, `open_remote` (`remote.py:91`) runs `link.new_chat` in its
   own task and awaits it shielded. If the turn is cancelled meanwhile, the chat is deleted as soon as its id
   arrives (`remote.py:96-106` `orphaned`).
6. A fresh `message_id = uuid4()` (`chat.py:186`). `link.complete` posts
   `{model, messages: self.wire(), stream: true, tool_ids: ["server:mcp:<tools>"], chat_id, id: message_id,
   params: {num_ctx}}` (`chat.py:188-191`). `params` is omitted when `context` is 0.
7. *(Inside Open WebUI; the source is not in this repo.)* Open WebUI runs the model. For each tool call it sends
   `POST /mcp` `tools/call` to the Hub with the Bearer key (§4.4). It feeds the result back to the model, saves the
   reply in the chat, and only then answers the completion with `null` (`link.py:258-259` docstring; the fake does
   the same, `tests/fakes/openwebui.py:87-94`). A streamed (SSE) answer is also read to its end
   (`test_assistant_tools.py:51-53`).
8. `link.saved` reads `GET /api/v1/chats/<chat_id>` and takes `history.messages[message_id]` (`chat.py:192`). A chat
   deleted in Open WebUI raises `GONE`. The Hub then drops `self.remote`, so the next message makes a new chat
   (`chat.py:193-196`).
9. Reading the saved message (`chat.py:197-208`): `content` is the text and `output` is the item list. If there is
   text, or `ran_tools(output)` finds a `function_call` item (`chat.py:57`), an `assistant` message is added with
   `seconds` and the `output`. A saved `error` (`_error`, `chat.py:62`) raises with Open WebUI's text, cut to
   300 chars. If there is neither text nor a tool call, the turn ends with `NO_TEXT`.
10. `Chat.turn` (`chat.py:210`) turns any `Invalid` into an `error` message and any other exception into
    `BROKEN` ("Something went wrong in the hub"). It then calls `purge()`, clears `busy`, and publishes
    `assistant.chat`. In tool-server mode it also starts a `sweep()` for leftover chats (`chat.py:222-223`).
11. On the next turn, `wire()` sends the kept messages with their `output` items, and `turns.lean` cuts older tool
    results (§4.2).

---

## 4.2 The conversation model

### 4.2.1 In memory only

- There is one `Chat` per module data dir, held in the module-level dict `_chats` (`chat.py:54`). It is created at
  module `start` (`chat.py:233`), which also deletes a `session.json` left by an older hub (`chat.py:234`).
- The messages are a Python list (`chat.py:75`). Each is `{id, role, text, at, ...extra}` with
  `id = secrets.token_hex(6)` (`chat.py:125-129`).
- Only `openwebui.json` is on disk. Tests assert that the assistant data dir holds nothing else, at mode 0600
  (`test_assistant_chat.py:59-62`, `test_assistant_tools.py:58-59`).

### 4.2.2 Roles

| Role | Shown? | Sent to Open WebUI? | Source |
|---|---|---|---|
| `user` | Kept in `view()`. The web reply column does not render it (`Chat.tsx:53-57`). | yes | `chat.py:134` |
| `assistant` with text | yes, with `seconds` | yes, with `output` if any | `chat.py:179`, `chat.py:202` |
| `assistant` with empty text (tools-only turn) | no: `view()` filters it (`chat.py:118-119`) | yes, with its `output` | `chat.py:201-203` |
| `error` | yes | never: `WIRE_ROLES = ("user", "assistant")` (`chat.py:49`, `wire` `chat.py:157`) | `Chat.turn`, `Remote.refused` |

`view()` (`chat.py:116`) returns `{busy, messages: [{id, role, text, at, seconds}], model}`. It never includes
`output` (`test_assistant_tools.py:225`). The web type is `ChatView` / `Msg` (`web/src/lib/protocol.ts:69-72`).

### 4.2.3 `keep`: purge after every turn (`turns.purge`)

- An "exchange" is one `user` message plus every message after it up to the next `user` message (`turns.py:1-5`).
- `turns.purge(messages, keep)` (`turns.py:39`) finds the indexes of the `user` messages. If there are more than
  `keep`, it **clears** every older dict in place (`m.clear()`) and returns the tail along with the count deleted.
  Clearing in place means nothing that still holds a reference can read the old message.
- `Chat.purge` (`chat.py:149`) runs after every turn (`chat.py:219`). If anything was deleted while an Open WebUI chat
  exists, that chat is deleted (`forget`) and `self.remote` is set to `None`. The next turn makes a new, empty chat.
  The docstring (`chat.py:24-25`) explains why this loses nothing: Open WebUI reads a chat's saved messages only for
  a `user_message`, which the Hub never sends, so the kept replies still reach the model through `output`.
- A changed `keep` applies when the next turn ends (`turns.py:6-7`, `test_assistant_purge.py:113`).

### 4.2.4 Lean history (`turns.lean`)

- `lean(sent)` (`turns.py:51`) works on the wire copy only. It finds the last `user` index. In every message
  **before** it, each `function_call_output` item is replaced by `_result` (`turns.py:59`). The replacement keeps
  type, ids and status, drops images, and sets the output to a single `input_text` holding `brief(text)`.
- `brief` (`turns.py:75`) keeps the first line, cut to `CUT = 120` characters (`turns.py:20`), and appends "…" when
  anything was left out.
- What is **not** cut: the newest exchange (the message being answered and anything after it), every
  `function_call` item (the model's own calls with their arguments, so it still sees its draft), `message` items, and
  the `content` text. The kept in-memory messages are not modified (`turns.py:9-14`,
  `test_assistant_lean.py:61`).
- The reason is given at `turns.py:10-12`: a tool result repeats the whole settings object as JSON, so a few
  exchanges overflow a small model's context (Ollama defaults to 4096 tokens).

### 4.2.5 Open WebUI chat lifecycle (`remote.py`)

| Event | What happens | Code |
|---|---|---|
| First tool-server message | `open_remote` → `link.new_chat`, title `"Hub"` | `chat.py:183-185`, `remote.py:91` |
| Each turn | completion into it; reply read back | `chat.py:188-192` |
| Purge deleted something | `forget(remote)`; `remote = None` | `chat.py:149-154` |
| New chat (`DELETE /api/assistant/chat`) | cancel the turn task, `forget(remote)`, empty messages, `busy = False`, emit `chat.cleared` | `chat.py:138-147`, `routes.py:93-99` |
| Session ended (`session.ended`) | `clear()` then `sweep()` | `chat.py:239-244` |
| Module stop | cancel and await the task, `forget(remote)`, then wait for every cleanup job | `chat.py:247-259` |
| Chat deleted in Open WebUI | `GONE` error line; next message makes a new one | `chat.py:193-196` |
| New chat while the chat is being made | `orphaned` deletes it when its id arrives | `remote.py:96-106`, `test_assistant_tools.py:176` |

- **Leftovers sweep.** `Remote.sweep` (`remote.py:68`) runs at module start (`chat.py:236`), after every tool-server
  turn (`chat.py:222-223`) and at session end. It does nothing with no key set. Under the lock (so it never deletes
  the chat a turn is making) it lists `GET /api/v1/chats/` and deletes every chat titled `"Hub"` except
  `self.remote` (`remote.py:23-36`). If the list cannot be read, it waits for the next sweep.
- **Refused deletes are shown once.** `delete` returns Open WebUI's reason for anything other than 200/404
  (`remote.py:39-49`). `refused()` (`remote.py:85-89`) adds the error line
  "Open WebUI did not delete the Hub's old chat: <reason>" only when the reason differs from the last one shown
  (`self.told`). The module docstring (`remote.py:3-6`) names the likely causes: an API key limited to some
  endpoints, or an account without delete permission.
- A New chat does not stop a turn that Open WebUI is already running. Its tool calls may still reach the Hub, and its
  late save lands in the deleted chat (`chat.py:139-140`).

### 4.2.6 `context` → `params.num_ctx`

- `settings.params(config)` (`settings.py:71`) returns `{"params": {"num_ctx": N}}` when `context` is not 0, and
  `{}` when it is 0. Both `ask` (plain) and the tool-server body use it (`chat.py:178`, `chat.py:191`).
- The reason, from the docstring (`settings.py:1-8`): Open WebUI merges request params over the model's params and,
  for an Ollama model, passes them on as Ollama options. Ollama then loads the model with that context instead of
  its 4096-token default, which a conversation with tool results overflows after a few exchanges. (The docstring
  names Open WebUI's `main.py merge_model_params` and `utils/payload.py apply_params_to_form_data`. These are not
  verifiable here.)

---

## 4.3 Settings → Assistant

### 4.3.1 Storage and validation (`settings.py`, `openwebui.json`)

- Store: `ctx.doc("openwebui", dict(settings.DEFAULTS))` (`chat.py:74`), which is `<data>/assistant/openwebui.json`.
- Defaults (`settings.py:21-22`): `url "http://127.0.0.1:3000"`, `key ""`, `model ""`, `tools ""`, `keep 6`,
  `context 8192`.
- `read(saved)` (`settings.py:44`): text fields fall back to the default when missing or not a string. `keep` goes
  through `turns.saved` (non-int → 6, else clamped 1–20). `context` goes through `saved_context` (non-int → 8192,
  ≤0 → 0, else clamped 2048–131072).
- `clean(changes)` (`settings.py:50`) applies to the PATCH body:
  - It must be a non-empty dict with keys only from `url, key, model, tools, keep, context`. Otherwise:
    "Only url, key, model, tools, keep and context can change" (field `settings`).
  - `keep` must be an int 1–20, not a bool: "Replies kept must be a whole number from 1 to 20" (`turns.count`).
  - `context` must be 0 or an int 2048–131072, not a bool (`settings.context`, `settings.py:28`).
  - Text fields must be `str`, at most 500 chars, and printable ASCII after strip (`link.printable`, `link.py:59`).
    This blocks CR/LF header injection (`test_assistant_chat.py:50-54`). The value is saved stripped.
  - A `url` must also pass `link.endpoint` (loopback numeric IP only).
- Route `PATCH /api/assistant/openwebui` (`routes.py:110`, body limit 4096, `manifest.py:18`) calls
  `Chat.configure` → `settings.patch(clean(...))` and returns the card view.

### 4.3.2 What the server reports (`GET /api/assistant`, `routes._view` `routes.py:40`)

```
{on, endpoints, clients, port,
 openwebui: {url, model, key: <bool>, tools, keep, context}}
```

The Open WebUI key is reported only as a boolean (`routes.py:44`). The MCP key is **not** in the view
(`test_cards.py:109`: "the key is shown once, when made; never in a view"). `POST /api/assistant/mcp-key` returns
`{mcp_key}` once (`routes.py:61-63`).

Other assistant routes (`manifest.py:14-23`): `PATCH ""` `{on}` (the access switch), `POST /mcp-key`,
`PATCH /port` `{port}` (calls `core.change_port`: 1024–65535, free on every bound address, saved, then a restart,
`runtime.py` `change_port`), `GET /openwebui/models`, `GET /openwebui/tool-servers`, and `GET|POST|DELETE /chat`.

### 4.3.3 What the screen shows (`web/src/modules/assistant/Card.tsx`)

- **Open WebUI** section:
  - Address field and API key field (password, placeholder "From Open WebUI: Settings → Account → API keys").
  - Tag "Key saved" / "No key". Save sends `url` always and `key` only when typed (`Card.tsx:39-45`).
  - Test re-lists models. Remove key sends `{key: ""}`.
  - Model select, filled from `GET /openwebui/models`; a saved model that is not in the list shows "(not listed)".
  - Tool server select ("None" plus the servers from `GET /openwebui/tool-servers`).
  - "Replies kept" (digits only, max 2) and "Context length" (digits only, max 6), each with its own Save. A refused
    value shows the server's line (`Card.tsx:54-65`, `Card.tsx:86-139`).
  - The models and tool-server lists are fetched on load whenever a key is saved (`Card.tsx:38`).
- **Access**: the "Assistant access" switch → `PATCH /api/assistant {on}` (`Card.tsx:80`, `Card.tsx:140-142`).
- **Connection**:
  - One CopyField per endpoint.
  - "MCP key" CopyField bound to `info.mcp_key`, plus a "New key" button.
  - The Open WebUI instruction line.
  - Port field. After a port change it shows "Restarting on the new port…" (`Card.tsx:143-156`).
  - See *Gaps* about `mcp_key`.
- **Clients**: the recent MCP callers (addr/name, age, status tag) from `McpAccess.clients()`, memory only, last
  10 minutes, at most 8 (`mcp.py:39-40`, `mcp.py:77-88`).
- **Card summary** (`routes.card`, `routes.py:66-75`), in this order: "Off" (off). Then "Refused a call from
  <addr>" (attention) if any recent client was refused. Then "On · no calls yet". Then "On · N client(s)".

---

## 4.4 The MCP endpoint (`hub/core/mcp.py`)

### 4.4.1 Transport subset

- One route: `POST /mcp`, JSON-RPC 2.0, protocol 2025-11-25, tools only (`mcp.py:1`). The route also accepts GET
  and DELETE so it can answer them with `405 Allow: POST` (`mcp.py:100-105`). The request body is capped at
  `1 << 20` bytes (`mcp.py:41`, `max_body_size`, Starlette 1.7.0).
- Stateless: no `Mcp-Session-Id` header (`test_mcp.py:64`). Replies are always `application/json`. No SSE stream.
- Supported versions: `VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")` (`mcp.py:37`). A present but
  unsupported `MCP-Protocol-Version` header gets `400 text/plain "Unsupported MCP-Protocol-Version"`
  (`mcp.py:114-117`). The docstring says that newer (2026-07-28) clients treat this as "fall back to initialize".
- `/mcp` is not a `http_route`. It is mounted directly (`runtime.py:135-137`), so the screen-cookie admission does
  not apply (`guard.py:7`). The outer `Guard` still applies the Host allow-list and the security headers
  (`guard.py` `Guard.__call__`).

Gates, in order (`McpEndpoint.endpoint`, `mcp.py:103-141`):

| # | Check | Answer |
|---|---|---|
| 1 | method ≠ POST | 405, `Allow: POST` |
| 2 | `Origin` present and not `http://<Host>` (`Gate.origin_ok`) | 403 "Origin not allowed" |
| 3 | access switch off | 503 "Assistant access is off" (whatever key is sent) |
| 4 | `Authorization` not `Bearer <key>` (scheme case-insensitive, `hmac.compare_digest`) | 401 "MCP key missing or wrong"; client recorded "Refused: MCP key missing or wrong" |
| 5 | unsupported `MCP-Protocol-Version` | 400 text/plain; client recorded "Refused: unsupported protocol version" |
| 6 | Content-Type not `application/json` | 415 "Send JSON" |
| 7 | body not JSON | 400, JSON-RPC `-32700 Parse error` |
| 8 | not an object or `jsonrpc != "2.0"` | 400, `-32600 Invalid request` |
| 9 | no `method`: has `id` (a response) → 202; else 400 `-32600` | |
| 10 | `method` not a string or `params` not an object | 400 `-32600` |
| 11 | no `id` (a notification) | 202, empty body |
| 12 | `id` is a bool or not a str/int | 400 `-32600 Invalid request id` |
| — | otherwise | client recorded "OK" (with `clientInfo.name` from `initialize`, cut to 60) → `handle` |

The peer address is taken from the socket, never from a header. `X-Forwarded-For` is ignored
(`test_cards.py:136-139`).

### 4.4.2 JSON-RPC methods served (`McpEndpoint.handle`, `mcp.py:143-159`)

| Method | Result |
|---|---|
| `initialize` | `{protocolVersion: <asked if supported else "2025-11-25">, capabilities: {tools: {listChanged: false}}, serverInfo: {name: "hub", version: VERSION}}` |
| `ping` | `{}` |
| `tools/list` | `{tools: [{name, description, inputSchema}]}`, in module load order, then declaration order |
| `tools/call` | unknown name → JSON-RPC error `-32602 "Unknown tool: <name>"`; else the call result |
| anything else | `-32601 "Method not found: <method>"` (e.g. `resources/list`, `test_mcp.py:95`) |

### 4.4.3 How tools are listed

- When modules load, `Core.load_modules` registers `tools_of(mod)` for every module into
  `self.tools[name] = (Tool, ModuleCtx)` (`runtime.py:131-132`). `McpEndpoint` receives that dict when the app is
  built (`runtime.py:135`). The list is fixed for the life of the process (`listChanged: false`).
- `features.tools_of(mod)` (`features.py:93`) emits, in this order:
  1. `mod.screen` → `get_<id>_settings` (no args) and `set_<id>_settings` (schema from the settings), where `<id>`
     is the module id with `-` replaced by `_` (`features.py:65-79`).
  2. each `Listing` → `list_<name>` with schema `{type: object, additionalProperties: false, properties: args,
     required?}` (`features.py:82-86`).
  3. each `Action` → its own name, its own schema (`features.py:89-90`).
- `value_schema(Setting)` (`features.py:36`) maps setting kinds to JSON Schema:
  - `text` → string with `maxLength = hi`.
  - `number` / `integer` → min/max from `lo` / `hi`.
  - `choice` → string, plus `enum` when choices are given.
  - `loras` → array of `{id, strength lo–hi, file readOnly}` (`lora_schema`).
  - `names` → array of at most `hi` strings of 1–120 chars.
  - `seed` → a string of length 1 to `len(str(hi))`, with the description suffixed by
    "random, or a whole number from lo to hi".
  - `Setting.text` becomes `description`.
- At this commit the modules that load by default publish ten tools: the six of Generate Image and Loras, then the four
  of the `sequence` module (`list_sequences`, `list_sequence_clips`, `add_last_clip`, `join_sequence`;
  `hub/modules/sequence/tools.py`, Stage 11). `media` publishes none, and `network` and `assistant` publish none
  (verified by enumerating `registry.discover()` + `tools_of`; pinned by `test_mcp.py:116-130`, which lists the ten in
  order). The `storyboard` module declares eight more (§4.9), but `modules_disabled` lists it by
  default (`hub/settings.py:39`), so `registry.discover` skips it (`hub/server.py:96`) and `tools/list` carries the ten
  until the name is removed from that list and the Hub restarts.

### 4.4.4 Argument checking (`hub/core/schema.py`)

- `check(schema, args)` (`schema.py:15`) treats `None` arguments as `{}`. It validates the object and fills
  **top-level** `default`s.
- Supported keywords (`schema.py:3-5`): type (object, string, integer, number, boolean, array), required,
  properties, additionalProperties (false or a schema), default (top level only), enum, minLength, maxLength,
  minimum, maximum, multipleOf, maxProperties, minItems, maxItems, items.
- Special cases:
  - `null` for a non-required known property is treated as left out (`schema.py:38-39`).
  - An integer written as a whole float (`15.0`) is accepted as `15` (`schema.py:63-64`).
  - A bool is never a number (`schema.py:66`).
  - An unknown key with `additionalProperties: false` → "unknown argument <key>".
- Each error is one plain line naming the path ("count must be at most 6", "prompt is required",
  "arguments must be an object"; `test_mcp.py:236-270`).

### 4.4.5 Result and error shape (`McpEndpoint.call`, `mcp.py:161-170`)

```
{"content": [{"type": "text", "text": <text>}], "isError": <bool>}
```

- On success, `text` is the tool's dict serialised as compact JSON (`separators=(",", ":")`,
  `ensure_ascii=False`), and `isError` is false.
- `Invalid` (including a schema failure) or `Refused` gives `text = e.text` and `isError: true`.
- Any other exception gives "Something went wrong in the hub" and `isError: true`.
- Tool failures are always a JSON-RPC *result* with `isError`, never a JSON-RPC error. Only an unknown tool name is
  a JSON-RPC error (`-32602`).

### 4.4.6 Access on/off and the key (`McpAccess`, `mcp.py:45-88`)

- Stored in `<data>/core/mcp.json` with default `{"version": 1, "enabled": false}` (`mcp.py:38`, `runtime.py:88`).
  Access is **off** by default.
- On first load the key is `secrets.token_urlsafe(32)` (`mcp.py:52-53`). The retired fields `key_hash`,
  `max_proposals` and `proposal_ttl_min` are scrubbed from disk (`mcp.py:42`, `mcp.py:50-51`).
- `rotate_key()` makes a new key, and the old key stops working at once (`test_cards.py:133-136`).
  `set_enabled(on)` saves the flag. Both call `on_change` = `Core.cards_changed`, which republishes the cards
  (`runtime.py:88`).
- The MCP key never opens `/api/*` (`test_guard.py:109-116`).

### 4.4.7 The "No Generate window is open" presence rule

- Implemented in the Generate Image module, not in the core. `screen._draft` (`generate_image/screen.py:223-233`)
  raises `Invalid("draft", "No Generate window is open")` when `ctx.bus.presence()["screens"]["workspace"]` is 0.
- It applies to a `draft` change and to a `references` change (`screen.py:247-249` calls `_draft(ctx, "")` before
  resolving references). Other settings (`steps`, `seed`, …) are saved without a window.
- It counts any connected **workspace-role** bus line (`hub/core/bus.py:77-85` `presence`). It does not check
  whether the Generate tab is the one visible.
- Over MCP the refusal comes back as `{"content":[{"type":"text","text":"No Generate window is open"}],
  "isError":true}` (`test_mcp.py:175-176`).

### 4.4.8 No logging

- `mcp.py` imports no logger and prints nothing.
- The server runs uvicorn with `access_log=False, log_config=None, log_level="error"` (`hub/server.py:45`).
- What remains of MCP traffic is the in-memory client list (address, client name, time, status), 8 entries,
  10 minutes (`mcp.py:77-88`).
- The assistant chat writes nothing either (`remote.py:6` "Nothing is written anywhere"; `chat.py:5-6`).

---

## 4.5 The system-prompt contract

### 4.5.1 What the Hub does not do

- The Hub adds no system message and no instructions. `wire()` emits only `{role, content}` plus the saved
  `output`, for `user`/`assistant` messages (`chat.py:157-168`). `link.ask` sends `{model, messages, stream,
  params?}` (`link.py:199-201`). The tool-server body is `{model, messages, stream, tool_ids, chat_id, id,
  params?}` (`chat.py:188-191`). The exact bodies are asserted in `test_assistant_tools.py:40-42` and
  `test_assistant_chat.py` (`test_a_message_goes_to_open_webui_as_is_and_the_reply_shows`).
- The chat docstring says "The hub adds nothing to the text" (`chat.py:4`). The card says the same on screen
  (`Card.tsx:89`).
- No tool description says *when* to call a tool (except the `Script:` sentence of three Generate actions
  and the script tools' field words) (`features.py:5-6`; `api.py` `Setting`: "a short factual label …
  never an instruction"; `Listing.text` / `Action.text`: "one factual line, ending with a period").
- When `generate_image` is called "is set in Open WebUI's system prompt"
  (`generate_image/tools.py:10`).
- The label "R6" that the brief uses for this rule does not occur anywhere in the repository (searched `docs/`,
  `hub/`, `web/src`, `tests/`).

### 4.5.2 What the Open WebUI system prompt is expected to carry

The prompt text lives in Open WebUI and is **not in this repository**. The points below are the contract given in
the brief. Each is listed with the Hub mechanism that supports it. The Hub enforces none of them.

| Expected instruction | Hub mechanism it relies on |
|---|---|
| First message of an idea: write the **draft only** (`set_generate_image_settings {draft}`), do not render | `draft` setting goes into the session panel, never the prompt box (`generate_image/tools.py:6-7`, `test_mcp.py:163-213`) |
| Later messages: **revise** the draft and call `generate_image` | `generate_image` renders the session's draft with the screen's settings (`generate_image/tools.py:50-78`); empty draft → "The draft is empty" |
| A message that only changes a setting: set it, do not redraft or render | `set_generate_image_settings` with only that key; saved like a screen change (`screen.py:235-257`) |
| Characters: find them with `list_characters`, put them in reference boxes via `references` | `list_characters` → `{characters: [{name, notes?}]}` (`cast.py:115-117`); `references` takes ≤3 names (`screen.py:42-44`) |
| Owner's notes on a character: use as background, once | Notes come only from `list_characters`; the Hub adds the notes to nothing (the change record) |
| Keep a picture's seed: set `seed` to one of `last_seeds` | `get_generate_image_settings` returns `last_seeds` (seeds of the last render of this model, memory only; `screen.py:193-196`); `seed` is the string "random" or a whole number |
| Continue the clip just made: read `last_clip`, set `references` to `[last_clip]`, then call `generate_image` | `get_generate_image_settings` returns `last_clip` (the id of the newest clip this screen made, `""` when none; `screen.py:183`). `references` takes that id alone (`cast.resolve`, `cast.py:74-112`), which puts the clip in box 1 of a model that continues one; the press then makes the scene longer and `frames` is the step (`generate_image/chain.py`, part 2, 2.10.7). A model that cannot continue refuses it in one line |

### 4.5.3 The tools exactly as the model sees them (`tools/list`, verbatim)

These were produced by running `registry.discover()` + `features.tools_of()` against this tree. The order and the
names are pinned by `test_mcp.py:122-126`. Open WebUI may present them with a server prefix. The fake uses
`hub_<name>` in its saved `output` items (`tests/fakes/openwebui.py:146-159`); the real prefixing is not
verified here.

The six below are the Generate Image and Loras tools. The sequence module's four follow them in `tools/list`
(`list_sequences`, `list_sequence_clips`, `add_last_clip`, `join_sequence`); their texts are in
`hub/modules/sequence/tools.py:61-68` and pinned by `tests/engine/test_sequence_module.py`.

1. **`get_generate_image_settings`**: "Settings of the Generate Image screen: draft, model, steps, guidance,
   megapixels, aspect, count, seed, loras, references."
   Schema: `{"type":"object","properties":{},"additionalProperties":false}`
2. **`set_generate_image_settings`**: "Set settings of the Generate Image screen: draft, model, steps, guidance,
   megapixels, aspect, count, seed, loras, references. Returns the settings after."
   Property descriptions (verbatim):
   - `draft` (string, maxLength 4000): "The assistant's draft prompt, shown beside the chat"
   - `model` (string): "Id of the image model, as list_image_models lists it"
   - `steps` (integer 1–100): "Steps the model runs"
   - `guidance` (number 0–50): "Guidance scale, for a model that has one"
   - `megapixels` (number, enum 1, 1.5, 2, 4): "Megapixels of the picture"
   - `aspect` (string, enum auto, 1:1, 4:3, 3:4, 3:2, 2:3, 16:9, 9:16): "Shape of the picture; auto is reference 1's
     shape, else 1:1"
   - `count` (integer 1–6): "Number of pictures made"
   - `seed` (string, 1–9 chars): "Seed of the first picture: random, or a whole number from 0 to 999999999"
   - `loras` (array of `{id, strength 0–2, file readOnly}`): "Active LoRAs of the model: id (as list_loras lists it)
     and strength"; `file`: "The file inside the model's folder, as get reports it"
   - `references` (array, maxItems 3, strings 1–120): "Reference pictures 1-3 by character name, as list_characters
     lists them, or last_clip alone to continue that clip; [] empties them."
3. **`list_image_models`**: "Image models that can run, with default size and steps." (no args)
4. **`list_characters`**: "Characters by name, with the notes on each, from the Characters folder."
   (no args)
5. **`generate_image`**: "Render the draft with the screen's settings, as the Generate button does." (no args)
6. **`list_loras`**: "LoRAs in a model's folder: id, name, trigger words from the file, default strength."
   Schema: `{"model": string}` required.

Declarations: `generate_image/screen.py:30-45` (settings), `generate_image/tools.py:81-93` (screen, listings,
action), `loras/tools.py:17` (listing). `push_draft` no longer exists. A call to it gets `-32602`
(`test_mcp.py:184-185`).

---

## 4.6 Shell and web plumbing

### 4.6.1 The bus client (`web/src/lib/bus.ts`)

- There is one WebSocket per window, to `ws(s)://<host>/bus` (`bus.ts:222-233`).
- On open, the client sends `hello` `{proto: 1, role, screen, label, subs: null}` (`bus.ts:96-98`). `screen` is a
  random `scr_XXXXXXXX` id (`bus.ts:59-61`).
- The server's `_hello` (`hub/core/bus.py`, `Bus._hello`) checks it. It subscribes the line to the default lanes
  for its role plus every module lane declared for that role. Module lanes are registered as
  `"<id>.<lane>"` → `("workspace", *mod.screens)` (`runtime.py:123-124`). The assistant's `lanes=("chat",)`
  therefore becomes `assistant.chat`, delivered to workspace lines.
- **welcome** carries `proto, boot, version, you{screen, role, lanes, device}, limits, tools, presence, focus` from
  the bus. `Core._welcome` adds `session, jobs, gpu, settings, cards` (`runtime.py:244-248`). The type is
  `Welcome` (`protocol.ts:44-52`).
- On welcome the client (`bus.ts:111-124`):
  - reloads the page if `boot` changed;
  - arms a silence watchdog of `limits.silence_s` (min 5 s);
  - sets the link to `on`;
  - replays the last `focus` and `sockets` declarations and any queued receipts (at most 20);
  - then emits `welcome` to listeners.
- **session.** `Session` (`hub/core/session.py`) opens when a window connects, with a new `id = token_hex(8)`. It
  ends when the last window has been gone for `session_grace_s = 15.0` (`hub/core/line.py:19`). Its end emits the
  core event `session.ended` (`runtime.py:106-109`), which the assistant hears (`manifest.py:28`). The web client
  compares `welcome.session`, and a new value drops what the window kept
  (`web/src/modules/generate-image/draft.ts:80-89`).
- **request/response.** `bus.request(t, d)` sends `{t, id: "r<n>", d}` and resolves on a `reply` / rejects on an
  `error` carrying the same `re` (`bus.ts:128-134`, `bus.ts:195-201`). When the line drops, every pending request
  is rejected with `{code: "unavailable", text: "Connection lost"}` (`bus.ts:36`, `bus.ts:141`). On the server,
  `install_handlers` registers `job.*`, `gpu.*`, `engine.start`. Any other dotted type goes to `module_call`, which
  looks up a module handler `"<id>.<name>"` (`hub/core/routes.py:112-125`). Errors come back as
  `error {code, text, field?}` (`Bus.dispatch`).
- **Close codes → link state** (`bus.ts:138-155`):
  - 4003 → `unpaired` (no retry);
  - 4009 (replaced) → a new screen id and an immediate retry;
  - 4000, or `going_off: shutdown` → `off` (slow checks);
  - 4013 → slow (30 s);
  - anything else → `cut`, backing off 0.5/1/2/4/8 s ±20 %, then every 30 s after 10 minutes.

### 4.6.2 `live.ts` stores

- `presence`, `jobs` (a `Map` by id), `focus`, `tools` and `connects` (`live.ts:6-11`), fed only by the bus
  (`feed`, `live.ts:13-37`).
- `connects` counts welcomes. Screens refetch their lists once per (re)connect. The chat uses it to `GET
  /api/assistant/chat` again after each welcome, then follows `assistant.chat` events
  (`generate-image/chat/assistant.ts:18-25`).
- `jobs` is replaced from `welcome.jobs`, updated by `job`, and pruned by `job.gone`.
- The store primitive is `createStore` (`store.ts:10-26`). It notifies only on an `Object.is` change. `useStore`
  wraps `useSyncExternalStore`.

### 4.6.3 Other `lib` helpers

- `http.ts`: `getJSON` / `sendJSON` / `sendBlob`, same-origin with credentials. A non-OK answer throws
  `HttpError(status, text, field)` built from the server's `{text, field}` (`http.ts:1-46`).
- `settingsOpen.ts`: a boolean store. Settings replaces the open tool while it is true.
- `keys.ts`: `isTypingTarget`, and `useCtrlEnter` (Ctrl/Cmd+Enter anywhere, no repeat).
- `toast.ts`: at most three toasts, each auto-dismissed after `ms` (default 4000).
- `desktop.ts`: detects HocusPocus Desktop from the UA (`HocusPocusDesktop/`). It reads `tags=2,3` and offers
  `hpd:instance/<n>` launch targets, or the Hub's own origin when no instance is tagged (`desktop.ts:1-20`). Used by
  the Generate Taskbar and the Media Bar (`generate-image/run/Taskbar.tsx:33`, `screens/media/Bar.tsx:38`).
  Pinned by `web/tests/unit/desktop.test.ts`.

### 4.6.4 Workspace and Settings screens

- `shell/Workspace.tsx`: tool tabs are the web module manifests (`shell/registry.ts`, `import.meta.glob`) that also
  appear in `welcome.tools`. The visible tab is reported with `bus.focus(id)` on change and on window focus. When
  Settings is open, a foot row holds `Live` and a "Close Settings" button (`Workspace.tsx:32-52`).
- `shell/Frame.tsx` puts the frame under the connection cover. `shell/ConnectionCover.tsx` shows:
  - "Server offline — reconnecting…" after a 1.5 s grace;
  - "Switched off" with "Check now";
  - "Not paired" with `hub pair --name <device>`.
- `shell/settings/Settings.tsx`:
  - `CoreList` sits on top.
  - Module cards are loaded from `GET /api/cards` and limited to modules that have a `modules/<id>/Card.tsx` panel.
  - They are sorted by `order` (Generate Image 880, Network 900, Assistant 920; `api.py` `Card`).
  - Clicking a card in the `Dock` opens its panel in place. `Dock` maps `network` → `net` and `assistant` →
    `chat` icons, and status dots ok / attention / off / error (`Dock.tsx:7-9`).
- `shell/settings/CoreList.tsx` (`GET/PATCH /api/settings`, reloaded on the `settings` bus event):
  - **Storage**: `Drive` and `Characters` paths (`PATCH {paths: {drive}}` / `{paths: {characters}}`;
    `CoreList.tsx:79-80`). The server checks them through `ui_patch` (`hub/settings_edit.py:17-42`, editable keys
    `paths: {drive, characters}`, `settings_edit.py:11`). The values come from `files.roots["drive"]` and
    `files.roots["chars"]` (`runtime.py` `settings_view`).
  - **Image engine**: engine folder (Found / Not found tag) and engine Python; the memory profile; the memory profile
    for video models ("Same as above" by default); and a switch per video size the engine reports, at least one and at
    most three on (`CoreList.tsx:83-108`; `coreSettings.ts`; part 1, 5.2).
  - `ImageModels`.
  - **Hardware**: GPUs; "Unload when idle" switch plus idle minutes.
  - **About**: version and Restart (`POST /api/settings/restart`).

### 4.6.5 The Network card and pairing

- The Network module (`hub/modules/network/manifest.py`) has routes:
  - `GET /api/network`;
  - `PATCH|DELETE /api/network/devices/{id}`;
  - `POST /api/network/pair`.

  Card order is 900. Bind and port are read-only here; they change only via `hub network set|reset`. The port can
  also change from the Assistant card (`admin.py:3-5`).
- `NetworkAdmin` (`hub/core/admin.py`):
  - `view` gives the server addresses and the devices with connected counts and `you`;
  - `pair_link` gives `{link: "<link_base>/pair#c=<code>", expires}`;
  - the card summary is one of: "<addr> not found on this server" (error), `Pairing open for "<name>"`
    (attention), or "Port P · N device(s) connected".
- `web/src/modules/network/Card.tsx` + `DeviceRow.tsx`: rename in place, and remove with confirmation. Remove is
  disabled for "This device" and for the "Last screen" (`DeviceRow.tsx:14`). The server enforces the same rules
  (`devices.py` `remove`). "Create link" shows the pairing link and its expiry.

**Pairing flow**

1. A code is made with `hub pair --name <n>` (`hub/__main__.py:205-208`) or "Create link" on the Network
   card. `Devices.mint_code` (`devices.py`) checks the name (1–40 printable chars) and makes the code
   `token_hex(16)`. It writes `{name, expires}` to `<data>/run/pair/<sha256(code)>` with a TTL of 600 s.
2. The device opens `/pair#c=<code>`. The route is `auth="pair"`: it is open to loopback, to known device
   addresses, and to anyone while a pairing code is open (`guard.py` `Gate.admit`).
3. `screens/pair/Pair.tsx` reads `#c=` and `next=` (`pair.ts` `readFragment`; `next` is restricted to this
   origin). It erases the hash with `history.replaceState`, then sends `POST /api/pair {code}`.
4. `web.py` `pair` (`hub/core/web.py:47-62`):
   - Rate limit (`Gate.pair_failed`): 5 failures within 60 s block the peer for 600 s, answered with
     "Too many tries. Wait 10 minutes." (429).
   - `Devices.redeem(code, peer)` is single use: it unlinks the code file and checks expiry. It replaces a device of
     the same name (case-insensitive) and keeps its id. It makes a new secret `token_urlsafe(32)` and stores only
     `sha256:` of it, with `addrs = [peer]`. It closes that device's old sockets.
   - The answer sets the HttpOnly, SameSite=Strict cookie `hub_screen = <id>.<secret>`, max-age 34,560,000 s
     (`web.py:19-24`, `guard.py:35`).
5. `Pair.tsx` then:
   - on success, `location.replace(next)`;
   - on 429, "Too many attempts";
   - on other 4xx, "This link is not valid or was already used";
   - otherwise, "Pairing failed" (`pair.ts:17-27`).
6. After pairing, a device is accepted only from the address it paired from. A moved device is told to pair again
   (`guard.py` `Gate.admit`, `Gate.repair`).

---

## 4.7 Tests that pin this behaviour

Python (`tests/core/`). The fake Open WebUI is `tests/fakes/openwebui.py`:

- **`tests/fakes/openwebui.py`.** A threaded HTTP server on 127.0.0.1 that records every request
  (`method, path, auth, body`).
  - It answers `/api/models`, `/api/v1/configs/tool_servers`, `/api/v1/chats/` (list), `/api/v1/chats/<id>`,
    `/api/v1/chats/new` and `DELETE`.
  - A completion with `stream` + `chat_id` saves `{content, output, error?}` into the chat and answers `null`, or a
    slow SSE stream (`stream_as`).
  - Knobs: `making` (delay chat creation), `delete_status` / `delete_detail`, `titles`.
  - `TOOL_OUTPUT` mirrors Open WebUI's saved output items.
  - Helpers: `tool_hub`, `settled`, `calls` (excludes sweep lists), `until`.
- **`test_assistant_chat.py`**:
  - settings are saved and the key is never shown;
  - validation of every field, including CR/LF injection and non-loopback URLs;
  - `openwebui.json` is the only file, at 0600;
  - plain mode sends the words as they are;
  - busy → 409;
  - every refusal (no model, 401, 400 detail, unreadable, refused connection) becomes an `error` line;
  - errors are never sent;
  - model and tool-server lists;
  - New chat empties the prompt box and the draft.
- **`test_assistant_tools.py`**:
  - the exact `new_chat` / completion / read sequence and bodies (including `tool_ids` and `params.num_ctx`);
  - output items go back on the next turn;
  - a saved error shows as an error;
  - a tools-only turn is kept but not shown;
  - stop and session-end delete the chat;
  - access off skips the turn;
  - a deleted chat starts a new one;
  - New chat during creation leaves none;
  - every settings turn carries the earlier tool calls.
- **`test_assistant_purge.py`**:
  - what an exchange is;
  - `keep` bounds and default 6;
  - the 7th exchange deletes the 1st;
  - a lower `keep` applies at the next turn end;
  - tool mode deletes the Open WebUI chat but keeps the tool calls;
  - without a purge the chat stays.
- **`test_assistant_lean.py`**:
  - `brief` (first line, 120 chars);
  - `lean` cuts older results on a copy;
  - `context` bounds and default 8192;
  - `num_ctx` is sent in plain and tool mode, and not sent when the value is 0.
- **`test_assistant_cleanup.py`**:
  - a refused delete is said once and the next sweep retries;
  - a different reason is said again;
  - the sweep deletes only chats titled "Hub";
  - 404 counts as gone;
  - the sweep never deletes the chat being made;
  - there is no sweep without a tool server.
- **`test_assistant_link.py`** (a raw-bytes fake):
  - loopback-only `endpoint`;
  - awkward but valid HTTP (chunked, 1xx, no length) is read;
  - bad answers become one sentence;
  - the size cap applies;
  - a silent Open WebUI times out;
  - the IPv6 Host header is bracketed;
  - a deleted chat is told apart from a refused key;
  - clearing mid-answer leaves nothing behind.
- **`test_mcp.py`**:
  - `initialize` negotiation and statelessness;
  - transport rules (405, version 400, Origin 403, 401, 415, 503);
  - JSON-RPC error codes;
  - the result shape;
  - the ten shipped tools (the six, then the sequence module's four) and their descriptions;
  - a `set` changes the screen;
  - the draft lands in the session, not the prompt box;
  - "No Generate window is open";
  - `generate_image` renders the draft;
  - `push_draft` is gone;
  - the key gates every call;
  - the `schema.check` cases.
- **`test_mcp_conformance.py`** + `mcp_driver.py`: official MCP SDK clients (`mcp==1.27.2`, which the docstring
  says is Open WebUI's, and 2.x) initialize, list and call against the real endpoint. These tests skip unless
  `HUB_MCP_VENVS` points at venvs with the SDK.
- **`test_features.py`**: names, descriptions and order come from the declarations; the set schema is built from
  the settings; `names` is a list of ≤ `hi`; listing and action schemas; the generated schema refuses bad values;
  the generated tools call the declared functions.
- **`test_registry.py`**: the manifest rules (§4.8), including generated tool names that collide across modules.
- **`tests/engine/test_storyboard.py`**, **`test_storyboard_render.py`** (with `storyboard_kit.py`): the eight generated
  tools, their names and texts; every tool refuses "No storyboards folder is set" while the folder is unset; a first cell
  from a character or the newest Temp picture makes the storyboard and its text round-trips; `move_cell` renumbers; the
  settings checks; the render drip (one cell waiting at a time, clips filed as `NN.mp4`, a failed cell stops the drip and
  names the cell); `draw_cell` lands as the cell and keeps its text. `tests/core/test_settings.py:114` holds
  the `modules.storyboard` defaults, and `tests/core/harness.py:92` discovers with the settings' `modules_disabled`, so the
  core and MCP tests see the ten tools that load by default (the six of Generate Image and Loras, then the sequence
  module's four), as above.
- **`test_cards.py`**:
  - the assistant view shape and that `mcp_key` is absent from it;
  - switch then key gating;
  - the client list and card summary;
  - rotation stops the old key;
  - the peer comes from the socket, not `X-Forwarded-For`;
  - the Network pairing link.
- **`test_guard.py`**: pairing flow and rate limit; the MCP key never opens the API.
- **`test_store_devices.py`**: codes are single use and stored hashed; expiry; re-pair by name keeps the id;
  rename/remove rules; damaged and older registries.

Web (`web/tests/`):

- **`e2e/chat.spec.ts`**:
  - an empty chat shows no New chat;
  - Enter sends, Shift+Enter is a newline, and Ctrl+Enter generates the draft;
  - Enter does nothing while busy;
  - the chat follows `assistant.chat`, and New chat empties the chat, the prompt box and the draft;
  - error lines are distinct;
  - the reply column shows replies with seconds and hides the typed messages and tools-only turns;
  - unknown roles are hidden.
- **`e2e/settings.spec.ts`** (Assistant cases):
  - access switch, endpoint, MCP key / New key, Remove key;
  - the key is sent only when typed;
  - the model list and model pick send only `{model}`;
  - the tool-server pick sends only `{tools}`;
  - a refused key shows the reason;
  - a non-loopback address is refused;
  - Replies kept and Context length save and show the server's line;
  - the port change;
  - Network rename / remove / pairing link.

  The specs run against mocks in `e2e/fixtures/api.ts`.
- **`unit/bus.test.ts`**: hello / welcome, replay of focus and sockets, backoff and jitter, off and restart codes,
  4003, 4009, boot reload, the silence watchdog, request/response by id and rejection on drop, the receipt queue,
  and wake.
- **`unit/desktop.test.ts`**: UA detection and tags.

---

## 4.8 Recipe: exposing a new module to the assistant

1. **Declare, do not hand-write tools.** In the module's `manifest.py`, set one or more of (`api.py` `Module`):
   - `screen=Screen(settings=(Setting(...), ...), read=async (ctx) -> dict, write=async (ctx, changes) -> dict)`.
     This publishes `get_<id>_settings` and `set_<id>_settings`. `write` receives a partial, already
     schema-checked dict and returns the settings after. It raises `Invalid` with a plain line.
   - `listings=(Listing(name, text, args_properties, fn, required=()),)`. This publishes `list_<name>`.
   - `actions=(Action(name, text, schema, fn),)`. This publishes `<name>`. `fn(ctx, args) -> dict` returns
     compact JSON.
2. **Pick setting kinds** from `choice, number, integer, text, loras, seed, names` (`api.py` `SettingKind`).
   Put the bounds in `lo` / `hi`:
   - `seed` and `loras` need both, with `lo < hi`.
   - `names` needs `hi ≥ 1`.
   - `text` uses `hi` as its max length.
   - `choices` must be strings for `choice` and numbers for `number` / `integer`. No other kind takes choices.

   (`registry.py:55-68`.)
3. **Write descriptions as labels only.** A description states what the tool or field is, never when to call it.
   - `Listing.text` / `Action.text` are one factual line **ending with a period**.
   - Every generated description must be non-empty, **≤ 200 characters** and end with "." (`registry.py:117-118`).
     A screen's generated text is built from the module title and the setting names (`features.py:77-79`), so a
     long title or many settings can exceed 200.
   - `Setting.text` is a short factual label ("Steps the model runs") and becomes the property `description`.
4. **What the registry refuses at start** (`registry.validate`, `registry.py:71-119`; the hub stops with
   `RegistryError: hub: module <id>: <rule>`):
   - a module id that is not kebab-case, or a reserved name (`api, assets, bus, cards, core, files, upload, mcp,
     pair, screen, settings, thumbs`), or a duplicate id;
   - screen settings that are empty, duplicated, or not snake_case (`^[a-z0-9_]{1,40}$`);
   - an unknown setting kind, or choices the kind cannot take; missing bounds;
   - a generated tool name that does not match `^[a-z][a-z0-9_]{0,63}$`, or that is already taken by any module
     (e.g. a `Listing("x")` next to an `Action("list_x")`, or an action named `get_<id>_settings` next to a
     screen);
   - an `input_schema` that is not a dict;
   - a description that is empty, longer than 200 characters, or does not end with a period.
5. **Keep schemas within `schema.py`'s subset** (§4.4.4). Anything else is silently not enforced. Defaults are
   filled only at the top level.
6. **Errors.** Raise `Invalid(field, text)` (or `Refused`) with one plain line. It reaches the model as
   `isError: true` with that text. Any other exception becomes "Something went wrong in the hub".
7. **Session-scoped state.** If a write must not outlive the session, guard it the way
   `generate_image/screen.py:223-233` does: check `ctx.bus.presence()["screens"]["workspace"]` and keep the value in
   memory, cleared on `session.ended`.
8. **Tell open windows.** Publish on a module lane (`ctx.bus.publish(lane, type, data)`; lane and type are
   auto-prefixed `<id>.`, `context.py:55-65`). Declare the lane in `Module.lanes` so workspace lines subscribe to it
   (`runtime.py:123-124`).
9. **Test.** Add a `test_features.py`-style check of the generated names, descriptions and schema, and a
   `test_mcp.py`-style over-the-wire `tools/list` / `tools/call`. Update the pinned tool list in
   `test_mcp.py:122-126`.
10. **Owner side.** New tools are listed only after a restart (`listChanged: false`). Whether and when the model
    calls them depends on the Open WebUI system prompt (§4.5), not on the Hub.

## 4.9 The storyboard module's tools (`hub/modules/storyboard/`, off by default)

The module is declarations only: a `Screen`, two `Listing`s, four `Action`s and one `listens` entry (`manifest.py:8-16`),
627 lines over six files; `routes.py` holds an empty tuple (`:6`) and the module has no tab, no lane and no jobs of its
own. It is listed in `modules_disabled` by default (`hub/settings.py:39`), so it is not loaded and its tools do not
exist; the ten tools (the six of 4.5.3, then the four of the sequence module) are all `tools/list` carries. With the name removed from that list (after a restart),
`features.tools_of` generates eight tools, each at most 200 characters, label-only and ending with a period
(`tests/engine/test_storyboard.py` pins the names and texts):

| Tool | From | What it does |
|---|---|---|
| `get_storyboard_settings`, `set_storyboard_settings` | `screen.SCREEN` (`screen.py:123`) | Seven settings: `storyboard` (the open one), `model` (the clip model), `picture_model`, `tier`, `aspect` (default `16:9`), `steps` (1–100), `seed` (`random` or a number; cell k uses it plus k − 1). Saved in the module's `settings` document (`screen.py:49-50`, `:119`). Each choice is checked against the live list when set: the storyboard against the storyboards folder, the models against the engine catalog, the tier against the clip model's tiers, the aspect against that tier's shapes (`write`, `:90-120`). The clip model has no default: a render is refused until it is chosen |
| `list_storyboards` | `cells.LISTINGS` (`cells.py:278`) | `{folder, storyboards: [{name, cells}]}` (`:258-259`) |
| `list_storyboard_cells` | `cells.LISTINGS` | Cells in order: `cell`, `id`, `seconds`, `camera`, `cast`, `text`, `clip` (the cell's newest clip, `clips_of`, `:181-193`); `rendering` while the drip runs; `stopped` with the reason after a stop (`:262-273`) |
| `put_cell` | `cells.ACTIONS` (`:284`) | Makes or replaces cell N: the picture from a character name or `newest` (the newest Temp picture, `Files.newest_temp`), the text, or both; a first cell makes the storyboard folder (`put`, `:222-243`) |
| `move_cell` | `cells.ACTIONS` | Moves cell N to place M and renumbers `01` onward through a passing name so no two cells share a stem (`arrange`, `:101-110`) |
| `draw_cell` | `render.ACTIONS` (`render.py:178`) | Queues one picture with the picture model and the cast's character pictures as references; the landed picture becomes cell N and keeps the cell's text (`draw_cell`, `:115-133`; `_landed`, `:136-147`) |
| `render_storyboard` | `render.ACTIONS` | Queues one clip per cell, every cell or the listed ones, in cell order (`render_storyboard`, `:78-102`) |

A storyboard is a folder exactly one level under `paths.storyboards`, a folder inside the Drive; its pictures in name
order are its cells (`01.png`, `02.png`…). A cell's text sits in the picture's one PNG text field, through
`Files.picture_text` and `picture_text_set` (part 1, 3.2): header lines `seconds`, `camera`, `cast`, a blank line, then
the clip text (`parse`, `write`, `cells.py:128-177`). With `paths.storyboards` unset every tool refuses with "No
storyboards folder is set" (`cells.py:17`, `top`, `:37-42`). The limits are `modules.storyboard.cell_text_max` (4000) and
`max_cells` (24) from `settings.json` (`cells.py:213`, `:120`).

`render_storyboard` is a drip: it submits the first cell as one `generate-image.image` job (`KIND`, `render.py:21`) with
the params a Generate press sends, and the job builder checks every value (`clip_params`, `:42-59`); the next cell is
submitted from the `job.finished` listener (`on_finished`, `:150-175`), so at most one cell of a storyboard waits in
the shared queue. Each landed clip is filed as `clips/<its day>/<storyboard>/<NN>.mp4` (`Files.file_clip`; a redo is
`NN-2.mp4`). A failed, cancelled or refused cell stops the drip and the stop names the cell (`_stop`, `:73-75`). The
cell's picture follows the clip model's role: a start-frame model opens on the cell picture, an identity model takes the
cast's character pictures and not the cell picture, and a model that takes none gets none (`:52-53`). The job's `by` is
`"storyboard"` (part 1, 3.4), so Generate Image's seed line is left alone (`build.on_submitted`, part 2). What is in
flight (`DRAWS`, `DRIP`, `ERRORS`, `cells.py:31-33`) is memory only.

Not built: any web part (a Storyboard tab or a Media section) and the roadmap decisions it waits on (part 8, 8.B).

---

## Gaps / unverified

- **MCP key is not shown in the real UI (code reading, not run).**
  - `GET /api/assistant` never returns `mcp_key` (`routes._view`, `routes.py:40-45`; asserted absent by
    `test_cards.py:109`).
  - `web/src/modules/assistant/Card.tsx` declares `mcp_key` on the GET type (`Card.tsx:16`) and binds the
    "MCP key" field to `info.mcp_key` (`Card.tsx:146`).
  - `newKey()` discards the `{mcp_key}` returned by `POST /mcp-key` and only reloads the view (`Card.tsx:78-79`).
  - Against the real server the field therefore has no value, even right after "New key".
  - The e2e mock returns `mcp_key` from GET (`web/tests/e2e/fixtures/api.ts:66`, `:161-163`), which hides this.
  - The `routes.py:1` docstring still says GET is "with `mcp_key`".
- **Stale full-stack spec.** `web/tests/full/stack.spec.ts:88-95` reads `mcp_key` from `GET /api/assistant` and
  expects `push_draft` in `tools/list`. Neither matches the server at this commit (`test_mcp.py:122-126`, `:184`).
- **Stale comments.** `chat.py:13` and `web/src/modules/generate-image/chat/assistant.ts:3` mention "the prompt box
  after a push". `push_draft` is gone.
- **"R6"** does not appear anywhere in the repo. The system-prompt text is not in the repo. The §4.5.2 items are the
  brief's contract mapped onto Hub mechanisms. The Hub enforces none of them.
- **Open WebUI internals** (`process_messages_with_output`, `merge_model_params`, `apply_params_to_form_data`, the
  Bearer header path, tool-name prefixing, the `server:mcp:<id>` interpretation) are taken from Hub docstrings
  (`chat.py:15-16`, `settings.py:4-8`, `mcp.py:8-14`) and the fake. They were not checked against Open WebUI 0.11.4
  source.
- **Docker reachability.** The MCP route still goes through the Host allow-list (`Guard`; `hosts()` =
  bind addresses + `localhost` when loopback is bound + `extra_hosts`, `hub/settings.py:250-255`). Whether a
  containerised Open WebUI's `Host` header matches depends on the deployment's bind / `extra_hosts`. That was not
  verified here.
- **The presence rule** counts any workspace-role window, not specifically a visible Generate tab
  (`screen.py:230`). A Media-only window does not count.
- **`test_mcp_conformance.py`** skips unless `HUB_MCP_VENVS` is set. Real-SDK compatibility is unverified by
  default runs.
- **No tests were run** for this section. The behaviour is taken from code and test reading. The tool list in §4.5.3
  was produced by importing the registry (`registry.discover()` + `features.tools_of`) under Python 3.13.16.
- Line numbers were read from a tree that was still being edited.
