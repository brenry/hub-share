# R25 — Director: what is still open, what the engine exposes for its prompt rules, what the server test must show (2026-10-17)

Research for BACKLOG item 9 (Stage 13 Director), after R21, R22 and R23. Facts only, no decision, no spec. Engine
citations are **upstream WanGP at `af2ed29`** (`install/install-engine.sh:14-15`), read in a clean clone at
`/tmp/upstream`, written `upstream <file>:<line>`. Hub citations are this repo at `6192541`. Two outside pages are
cited with their dates; neither is about the installs on the server.

## 1. What R23 left unverified
Listed by R23 itself ("Not checked here"):
- **HocusPocus 0.10.0, all of it.** R21's `HP:` cells: the 0.22 s per syllable and pause constants, the 2.1 words/s
  budget (`minimax_h3_duration.py`, `h3_dialogue.py:652-690`), the schema, compiler, validator and guarded polish
  line numbers. Nothing of HocusPocus is in this repo or reachable from it (HANDOFF §6).
- **The Maestro version.** R23 read public `Blizaine/Maestro` `31d7396` (2.6.0); the server's install is not recorded.

Carried from R22 §F, not taken up by R23:
- NOT FOUND upstream: a two-speaker video example; a continuation (`video_source`) prompt; an end-image or injected
  frame alignment line other than the 0.00 s start line (the rule is stated in prose only:
  upstream `models/minimax_h3/prompt_enhancer.py:30`); any `<scenetrans>`/`<cutoff>` example; the form of a Ref2VA
  keyframe `<Picture N>` in `subject_definitions`; any prompt token limit.
- Contradiction 1 (blank lines between Ref2VA sections against `PG`/`PW` splitting) — not re-read here.
- Contradiction 5 — **re-read here, holds.** Both soundtrack-mode templates lack the lip-sync wording the rules ask
  for (`audio_prompt_type` `A`: upstream `shared/deepy/settings/gen_video_with_speech/MiniMax H3 FL2VA Pruned PDD 8
  Steps With Sound.json:9`, `:11`, and `… FL2VA Pruned Turbo Lightx2v 8 Steps With Sound.json:9`, `:11`; `AS`:
  `… Ref2VA Pruned Turbo Lightx2v 8 Steps With Sound.json:9`, `:11`), and the Ref2VA one names "the supplied
  soundtrack", against "without mentioning a supplied audio track" (upstream `prompt_enhancer.py:34`).
- Contradiction 6 — **re-read here, holds.** `defaults/minimax_h3_fl2va_pdd.json:19` has
  `integrated_multimodal_description` and `overall_soundscape`, no `non_diegetic_music`.

Left open by R21 §7 and not settled since:
- **The Open WebUI → backend grammar claim.** R21 §4.1: "llama.cpp enforces tool-call arguments as a grammar" and
  §7 "R19 says Native mode, Tool Search off". R19 does not exist (HANDOFF §4). **Which backend serves the configured
  assistant (llama.cpp, Ollama, another), which model, and which Open WebUI version: not recorded anywhere in this
  repo.** The claim has no source here.
- Lip-sync quality and the mouth during computed silence: unmeasured (R21 §7, citing R20, which does not exist).
- The speech pace the Hub would use: R23 decision 2 makes it a setting measured on the server's GPU; no measurement exists.

## 2. What the engine exposes today for reading its own prompt rules
**Where the rules live.** Each model definition carries two prose strings: `deepy_prompt_infos` (short, written for
an agent) and `prompt_infos` (long, for the UI); plus `deepy_infos` / `infos` for settings. For H3:

| Definition | `deepy_prompt_infos` | Set at | Length in the Hub's capture |
|---|---|---|---|
| FL2VA, `_pdd`, `_veda`, `vdn` and pruned | `FL2VA_DEEPY_PROMPT_INFOS` (`prompt_enhancer.py:23`) | handler `:794-795` | 2844 |
| Ref2VA and its variants | `REF2VA_DEEPY_PROMPT_INFOS` (`:108`) | handler `:717-718` | 3105 |
| Control, control pruned | `FL2VA_DEEPY_PROMPT_INFOS` | handler `:541-542` | 2489 |
| Viggle | a fixed one-liner | handler `:504` | — |
| `minimax_h3_tts_ref2va_pruned` | `H3_AUDIO_DEEPY_PROMPT_INFOS` (`:123`), since `H3_DIALOGUE_GENERATION = True` (`dialogue.py:16`) | handler `:418` | 1018 |

Handler lines are upstream `models/minimax_h3/minimax_h3_handler.py`. The still-image text is appended to both
strings for image mode (`:854-855`). Lengths: `tests/fixtures/contract/upstream-18.05/engine.json`, counted here;
the control length differs from FL2VA's, so its string is not the bare constant (not traced further).

**The rules are prose, not data.** Field names, `[Shot N]`, `<d>[Language] …</d>`, the alignment sentence, `N/A`
and the `PW` rules appear only inside the text (`prompt_enhancer.py:23-37`). No list or tuple of field names, no
regex, no schema is exported by the H3 module. R21 §1.3 calls these "machine-readable form": the *place* is
machine-readable (a known key per definition); the rules inside are sentences. The structured fields beside them
are `audio_prompt_type_sources` (letters, labels; handler `:769-785`, `:821-833`), `sliding_window_defaults`,
`preserve_empty_prompt_lines` (tts only, `:357`).

**The engine's own readers of these keys:**
- Deepy's tool `gen_video_with_refs` returns them as `input_guidance` and `prompt_guidance`
  (upstream `shared/deepy/engine.py:1923-1924`).
- The engine's MCP server: `_mcp_model_definition` serves `deepy_infos` / `deepy_prompt_infos` under the names
  `infos` / `prompt_infos` when `help_detail="agent"`, the UI text when `"full"`; strings over a limit are cut with
  "[Truncated, query property …]" (upstream `shared/mcp/server.py:562-583`). Tools `wangp_model` (`server.py:1777`)
  and v2 `wangp_model` action `definition` with `property` and `detail` agent|full (`shared/mcp/v2.py:344-350`, `:365`).
- `list_model_defs` returns definitions with callables stripped (upstream `shared/api.py:611-617`), which the
  Hub's adapter already calls (`hub/worker/adapters/upstream.py:66`, `LISTING`).

**What the Hub has of them today.**
- Captured whole: `--dump-engine` writes each definition as `plain(model_def)` (`hub/worker/enginedump.py:96-100`),
  so the fixture holds every H3 `deepy_prompt_infos`, `prompt_infos` and `audio_prompt_type_sources`.
- Read nowhere: no file under `hub/` names `deepy_prompt_infos` or `prompt_infos` (grep, this commit). The upstream
  adapter's `READS["definition"]` lists the family fields, `sliding_window_defaults`, `image_ref_choices` and others,
  not these (`hub/worker/adapters/upstream.py:67-76`). A reader would be a new `READS` entry (contract test).
- The Hub reaches the engine in-process through its worker, not through the engine's MCP server; the server's
  `agent`/`full` switch and truncation are not on the Hub's path.

## 3. The one server test: what it would have to show
Source of the test: R21 §7, R23 decision 4. What is known here:
- The Hub's MCP endpoint lists each tool's `inputSchema` as declared (`hub/core/mcp.py:151-153`).
- **No Hub tool has a nested object argument today.** `hub/core/schema.py:1-5` covers "the hub's flat tool schemas";
  the deepest argument is an array of strings or integers (`hub/modules/storyboard/render.py:183-189`). It supports
  nested `object` and `items`, and no `pattern`, `anyOf`, `oneOf` or `$ref`.
- Open WebUI supports MCP (Streamable HTTP) natively from v0.6.31 (docs.openwebui.com/features/extensibility/mcp,
  read 2026-10-17). Nothing found on how it passes a nested `inputSchema` to the backend.
- llama.cpp builds a grammar from tool schemas for tool calls; a string `pattern` inside array `items` made it fail
  with HTTP 400 "failed to parse grammar" (github.com/ggml-org/llama.cpp/issues/25895, 2026-07-19, build b454,
  closed as a duplicate of the nested-pattern grammar bugs). Whether the server runs llama.cpp is not known (§1).

What the test would have to show, each one a thing readable off the server:
1. **The inputs, first:** the backend's name and version, the model, the Open WebUI version, and its function
   calling mode for that model. Without these, no result below can be read.
2. **The schema reaches the backend unflattened:** the `tools` entry Open WebUI sends keeps the nested object with
   its `properties`, `required` and `additionalProperties: false` (seen in the backend's request log or Open WebUI's
   debug output).
3. **The call comes back nested:** the model's tool call reaches the Hub's `/mcp` with an object inside an object
   and an array of objects, and it passes `schema.check` (`hub/core/schema.py:15`).
4. **Constrained or only prompted:** whether the backend enforces the schema as a grammar (a malformed argument
   cannot be produced) or only shows it to the model. One good call does not tell these apart; the backend's
   settings or log must say which.
5. **No grammar refusal:** the request is not refused at grammar build (the llama.cpp case above), with all of the
   Hub's tools listed at once, not the test tool alone.

What it would not show: whether the prose rules are followed, Director quality, or speech timing. The test needs a
tool with a nested schema, which the Hub does not have; making one is a spec's or build's choice, not taken here.

## 4. NOT FOUND
- A structured (non-prose) export of H3's field names or tags anywhere in upstream `models/minimax_h3/`.
- Any record of the server's LLM backend, model, Open WebUI version or function-calling mode in this repo.
- R19 and R20, cited by R21 §7.
- Open WebUI documentation on nested `inputSchema` handling in native function calling.
- Everything of HocusPocus.
