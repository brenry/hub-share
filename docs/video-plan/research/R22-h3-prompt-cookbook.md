# H3 prompt cookbook — MiniMax H3 prompt syntax and how it is enforced

Status: 2026-10-15, read-only research, nothing run. Written for the Hub's assistant (Open WebUI + Hub MCP tools).

## Sources, licenses, citation keys

| Key | Source actually read | License file |
|---|---|---|
| `E:` | Upstream WanGP 18.05, git commit `af2ed29` (`E:wgp.py:186` `WanGP_version = "18.05"`). This is a clean clone, not the installed engine. Line numbers hold for the installed engine only if it is the same commit. | `E:LICENSE.txt:1-2` "WanGP Community License 2.0" |
| `M:` | Maestro, public repository `github.com/Blizaine/Maestro`, commit `31d7396`, `M:VERSION` = `2.6.0`. This is not the server's install, whose path and version were not reachable. | `M:LICENSE:4-6` "WanGP Non-Commercial Evaluation License 1.1"; full text at `M:app/LICENSE.txt` |
| `H:` | HocusPocus, the server's install | **NOT FOUND (not reachable)**: the server was not reachable, and no public copy exists |

**What "path:line" means here.** `E:x:n` is `engine/app/x` at line n. `M:x:n` is `x` at line n under Maestro's repository root (the WanGP fork lives in `M:app/`).

**How the citations were checked.** The citations were gathered in three read-only passes. About 40 of them were then re-read at the cited lines before writing.

---

## 0. Five facts that shape everything else

1. **The engine does not parse the H3 grammar.**
   - The prompt string goes to the Qwen3-VL text encoder whole, after the media labels (`E:models/minimax_h3/pipeline.py:483-501`, `:1109`; `E:models/minimax_h3/text_encoder.py:124-155`).
   - No code reads the section names, `[Shot N]`, `<d>` or `(Sx)`. The one exception is a single paragraph-boundary check that knows two field names (`E:shared/utils/prompt_parser.py:62-78`).
   - The syntax is a contract with the model, stated in prose by the engine. A wrong prompt is accepted and simply generates worse.
2. **What the engine does enforce:**
   - line and paragraph splitting;
   - `#` comments, `!` macros and `{var}` templating;
   - `[/…]` window commands;
   - `Speaker N:` scripts on the audio-only model;
   - the order in which `<Picture/Video/Audio N>` media are shown to the model (§A.1).
3. **The engine publishes its own prompt rules as model-definition data.**
   - Its own MCP server serves the agent version to any agent (§B.1).
   - The Hub can read the rules from the engine instead of hard-coding them.
4. **Maestro has no MCP server and no tool/function-calling definitions.** A search for `mcp|modelcontextprotocol|fastmcp` over the whole repo finds nothing. Director Mode enforces the grammar differently:
   - grammar-constrained JSON on its own LLM (`M:app/services/llm_service.py:2531-2535`);
   - a deterministic compiler that writes the H3 text;
   - a validator that runs before any GPU job (§B.2).
5. **HocusPocus could not be read.** Every HocusPocus cell below is NOT CHECKED.

---

## A. H3 prompt grammar (engine = ground truth)

### A.1 What the engine itself parses (enforced in code)

| Rule | Evidence |
|---|---|
| **How prompt lines are processed** (`multi_prompts_gen_type`) | |
| `G` = each line is a new queued generation | `E:shared/utils/prompt_parser.py:22-33` |
| `PG` = each paragraph is a new queued generation | same |
| `W` = each line is a new sliding window | same |
| `PW` = each paragraph is a new sliding window of the same video | same |
| `FG` = all lines are one prompt | same |
| Legacy values map as `{0:"G",1:"W",2:"FG","":"FG",…,"P":"PG"}` | `:19` |
| The default mode is `PG` | `:8` `DEFAULT_MULTI_PROMPTS_MODE = "PG"` |
| **Line and paragraph handling** | |
| `FG` keeps the whole text, `P` modes split on blank lines, other modes split on lines | `prompt_parser.py:35-60` |
| Lines starting with `#` are removed (usable as window titles) | `:42`, `:220-221` |
| A line starting with `!` is a macro line | `:224` |
| Empty lines are dropped unless the model sets `preserve_empty_prompt_lines` (the audio model does, `E:models/minimax_h3/minimax_h3_handler.py:357`) or the mode is a `P` mode | `:215-218`; `E:wgp.py:1073` |
| A `{x}` in a line raises "Unknown variable", except in a `Speaker N {…}:` header | `prompt_parser.py:7`, `:298-304` |
| **Window commands** | |
| Regex: `SLASH_BLOCK_RE = re.compile(r"\[\s*/\s*([^\]]+?)\s*\]", re.IGNORECASE)`. Brackets that do not start with `/` (`[Shot 1]`, `[English]`) are untouched | `E:shared/utils/frame_scheduler.py:9` |
| The allowed commands: `WGP_SLASH_COMMANDS = {"duration", "overlap", "new_shot", "no_end_image", "loras_mult"}` | `frame_scheduler.py:8` |
| An unknown command raises "Unknown prompt command '/{key}'…" | `:144-146` |
| H3 overlap is normalised to `1 + 17k`; `/overlap=0` equals `/new_shot` | `frame_scheduler.py:105-131`; `E:models/minimax_h3/minimax_h3_handler.py:905-908` |
| **Windows and paragraphs** | |
| When there are fewer prompts than windows, the last prompt is reused: `prompt = prompts[window_no] if window_no < len(prompts) else prompts[-1]` | `E:wgp.py:7816` |
| `PW` paragraph check: an error tells the writer to "Keep every line and labeled section belonging to one window adjacent with single newlines, and use exactly one blank line between complete windows." | `prompt_parser.py:62-78` (called at `E:wgp.py:1085-1087` and `E:shared/mcp/preflight.py:86`) |
| **Media labels** | |
| Media headers come before the prompt, counted per type: `<Picture n>: `, `<Audio n>: `, `<Video n>: ` | `E:models/minimax_h3/text_encoder.py:124-155` |
| Picture order: start or continued frame, end image, injected frames, then reference images | `E:models/minimax_h3/pipeline.py:941-996` |
| A kept soundtrack (`S`) gets no `<Audio N>` | `pipeline.py:1029` |
| **Audio-only model** | |
| It switches to script mode when `^\s*Speaker\s*(\d+)\s*(?:\{([^{}\n]*)\})?\s*:\s*` matches | `E:models/minimax_h3/dialogue.py:44`, `:113-114`; `pipeline.py:760` |
| **Tokens** | |
| No token limit or truncation on the H3 prompt: **NOT FOUND** | (text_encoder has no `max_length`) |

### A.2 FL2VA — First / Last ("T2VA/I2VA"); also `_pruned`, `_pdd`, `vdn`, `veda` and the control models

**Which models this covers.**
- The rules are published as `deepy_prompt_infos = FL2VA_DEEPY_PROMPT_INFOS` (`E:…/minimax_h3_handler.py:795`; control models `:542`) and `prompt_infos = FL2VA_PROMPT_INFOS` (`:658`).
- Pruned, PDD, VDN and Veda variants get the same text (`:795`, `:837-855`).

**Section order and forbidden elements:**
- **Exactly three fields, in order:** `integrated_multimodal_description`, `overall_soundscape`, `non_diegetic_music` (`E:models/minimax_h3/prompt_enhancer.py:252`).
- **No blank lines inside a window** ("Use these three fields together, with no blank lines inside a window", `:25`).
- **Output only the prompt:** "with no commentary, Markdown, or code fence" (`:250`).
- **English description:** "Write all descriptive material in English. Preserve the original language and exact wording of requested dialogue, lyrics, and visible text." (`:252`)

**Shots and cuts:**
- "Begin with [Shot 1] without a timestamp. A later hard cut begins `[Shot N] At MM:SS.mmm, ...` using a strictly increasing time within the requested duration." (`:254`)
- "Add a cut only when it conveys new subject, space, state, viewpoint, or time information; use natural camera movement for a small framing change." (`:254`)

**Speakers and speech:**
- "Use stable speaker IDs such as (S1) across the whole timeline. Put only the exact spoken or sung content inside `<d>[Language] ...</d>`." (`:256`)
- The form is `says (S1) <d>[English] Made it.</d>` (`:26`).
- **Across a cut:** "If speech crosses a cut, put `<scenetrans>` at the connection in both shots and explicitly say it continues across the cut. Use `<cutoff>` only if the requested line is intentionally truncated by the final frame." (`:256`)

**Sound fields:**
- "overall_soundscape is one compact paragraph covering ambience, physical action sounds, and non-verbal human sounds; do not repeat dialogue or singing."
- "Write `non_diegetic_music: N/A` when no score is requested." (`:258`)

**Frame anchors** go before the fields:
- "`For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` Start-only uses Picture 1 at zero; end-only uses Picture 1 at the exact end and final shot; both use Picture 1 at zero and Picture 2 at the end." (`:30`)
- With images, write "one alignment line per timeline picture in time order" (`:275`).
- `FL2VA_IMAGE_SYSTEM_PROMPT` then asks for "one blank line before the three core fields" (`:275`). That blank line would split a `PW` window (§F, item 2).

**Soundtrack mode** (`audio_prompt_type` `A`/`K`):
- For visible speech, "explicitly include `speaking with natural lip movements synchronized` or equivalent wording … without referring to a supplied audio track or assigning it an `<Audio N>` label." (`:34`)
- "Outside soundtrack mode, requested speech must still include the exact spoken words in `<d>[Language] ...</d>`." (`:34`)

**Exceptions:**
- **Viggle ignores prompt text.** "Viggle uses a fixed built-in prompt; generation text is ignored." (`E:…/minimax_h3_handler.py:504`; `pipeline.py:494-495`)
- **Image mode** (`image_mode 1`) uses a still prompt with no shots, timestamps, `<d>` or soundscape (`prompt_enhancer.py:315`).

### A.3 Ref2VA — Reference / identities ("Omni"); also `_pruned` and its variants

**Which models this covers.** The rules are published as `deepy_prompt_infos = REF2VA_DEEPY_PROMPT_INFOS` (`E:…/minimax_h3_handler.py:718`) and `prompt_infos = REF2VA_PROMPT_INFOS` (`:658`).

**Six sections, in order:** `subject_definitions, summary, retention_analysis, detailed_description, overall_soundscape, non_diegetic_music` (`E:…/prompt_enhancer.py:284`).

**The `summary` field:**
- It begins with bracketed task tags chosen from: keyframe completion, reference generation, video editing, video continuation, audio reuse, audio reference (`:288`).
- Tags combine with ` + `, e.g. `[reference generation + audio reference]` (`:110`, `:166`).

**The `retention_analysis` field:**
- One line per retained label (`:290`).
- Visual modes: `fully_preserved`, `partially_preserved`, `attribute_transfer`, `weak_reference`. Audio modes: `fully_copy`, `partially_copy`, `reference`, `weak_reference` (`:290`).
- Line form: `<Subject 1> (appears in [Shot 1]): fully_preserved - …` (`:146`, `:197`).

**Labels:**
- `<Subject N>` is reusable visible content.
- `<Picture N>` is a concrete image. It gets its own entry only as a keyframe, composition anchor, edited frame or storyboard.
- `<Video N>` is a whole-video role; `<Audio N>` is copied or referenced sound.
- Each type is numbered independently (`:286`).
- A reference image is defined as `<Subject N>` from `<Picture N>`, with no time (`:308`).
- Start, end, continued and injected frames are keyframes with their own `<Picture N>` entry and a time, plus keyframe completion and `fully_preserved` (`:310`).

**Speakers:** "A speaking referenced subject is written `<Subject N> (Sx)`" (`:294`), for example `<Subject 1> says (S1) <d>[English] I was afraid to speak.</d>` (`:182`).

**The `detailed_description` field:**
- It starts with the global treatment, then `[Shot 1]`. Later shots are `[Shot N] At MM:SS.mmm` (`:292`).
- Length: "aiming for roughly 350-500 English words for reference-generation tasks unless the dialogue timeline requires a different length" (`:292`).

**Picture numbering per window:** start or continued frame (`<Picture 1>`), end image, the window's injected frames by time, then reference images (`:120`; `E:…/minimax_h3_handler.py:109`).

**Kept soundtrack (`AS`, `KS`):** "A kept soundtrack is not a reference: give it no <Audio N> label." (`E:…/minimax_h3_handler.py:113`; enforced at `pipeline.py:1029`)

**Limits:** at most 9 images, 3 videos (each ≥ 2 s), 3 audio references (each ≥ 2 s), 12 files in all; audio references ≤ visual references (`E:…/minimax_h3_handler.py:115`, `:985-1067`).

**A trap with blank lines:**
- The UI skeleton and the voice example put blank lines between sections (`prompt_enhancer.py:136-156`, `:224-238`). Under `PW`/`PG` those split the prompt.
- Only `:157` warns about it: "Dont't keep any empty lines between prompt sections when using sliding windows…"

### A.4 Pruned versus full models

**NOT FOUND:** no prompt rule depends on pruned versus full, or on PDD/VDN.
- The same `deepy_prompt_infos` are assigned to every variant (`E:…/minimax_h3_handler.py:718`, `:795`).
- Only steps and samplers differ: PDD needs exactly 8 steps and Euler (`:900-904`).

### A.5 Audio-only — `minimax_h3_tts_ref2va_pruned`

**Script grammar** (`E:models/minimax_h3/prompt_enhancer.py:123-132`, published as `deepy_prompt_infos`, `E:…/minimax_h3_handler.py:418`):
- "For speech, write the exact words in `prompt`, one turn per `Speaker N:` block. Put language, emotion, pace and acting directions in square brackets; these are not spoken."

**How the engine parses it** (`E:models/minimax_h3/dialogue.py`):
- **Header:** `_SPEAKER_HEADER` (`:44`). Optional options in braces: `Speaker 1 {French, calm}:` (`:91-98`).
- **Directions:** `_DIRECTION = re.compile(r"\[([^\[\]\n]+)\]")` (`:45`). Every `[…]` is an unspoken direction, split on commas (`:127-128`).
- **Text:** a turn with no text outside brackets raises "MiniMax H3 dialogue Speaker {n} has no spoken text" (`:130-131`).
- **Language:** the first direction item that equals a `_LANGUAGES` key sets the language (`:46-62`, `:101-110`). Keys include `en`/`english`/`anglais`, `fr`/`french`/`francais`, `de`, `es`, `it`, `ja`, `ko`, `zh`/`mandarin`, `pt`, `ru`, `ar`, `hi`, `nl`, `pl` and `tr`.
  - Otherwise the language is "Original language".
  - A turn without one inherits the speaker's earlier language (`:134-137`).
- **Voices:** Speakers 1, 2 and 3 take audio guides A, B and D. Other speakers reuse their first generated turn (`:363-371`, `:427`).

**Timing:**
- Per turn: `max(4.0, min(45.0, words/2.6 + 0.18*count([.!?;:]) + 1.4))` (`:148-151`; `H3_DIALOGUE_WORDS_PER_SECOND = 2.6`, `:23`).
- Total: `min(duration_seconds, 300)`, with 0.18 s pauses between turns (`:159-169`).
- `duration_seconds` must be 4–300 (`E:…/minimax_h3_handler.py:874-880`).

**Compiled prompt.** Each turn becomes a six-section Ref2VA prompt with `Speaker {n} (S{n}) … says exactly, <d>[{language}] {text}</d> The line is complete and no other dialogue is spoken.` (`dialogue.py:175-201`).

**Enhancer-only rules** (system prompts, not checked by code):
- monologue: "exactly one `Speaker 1:` block", "Write 4-8 sentences" (`prompt_enhancer.py:349-356`);
- dialogue: "Every turn must be one separate `Speaker N:` block", "Write 6-14 turns" (`:367-375`);
- no `<d>`, XML or section names (`:349`).

**Mode and windows:**
- The factory mode is `"FG"` (`E:…/minimax_h3_handler.py:1232`).
- Window commands are refused on this model: "Prompt slash window commands require a video model with Sliding Window support." (`E:wgp.py:1093-1094`)

### A.6 Length limits and timing

**Window lattice:**
- Frames are `17k + 5` with `frames_minimum 107` (`E:…/minimax_h3_handler.py:581-583`).
- Window 124–481, default 362. Overlap 1–120, step 17, offset 1, default 18 (`:796-797`; Ref2VA `:719-720`). The control models have a window maximum of 362 (`:546-547`).
- "MiniMax documents an official duration of 4–15 seconds per generation window" (`:106`).

**Words per second in video speech: NOT FOUND upstream.** Only the audio model's 2.6 exists (`dialogue.py:23`).
- Maestro uses 2.8 by default and 3.0 at most (`M:app/services/dialogue_timing.py:6-7`).

**Prompt token limit: NOT FOUND upstream.** Maestro contradicts itself:
- its guide says "must target 450 or fewer Qwen text tokens and must never exceed 480. This is a real model-input limit" (`M:app/services/llm_guides/enhance/minimax_h3_video.md:9-11`);
- its code says "MiniMax H3 does not publish a 512-token prompt limit … must never act as a generation gate", with `H3_PROMPT_QUALITY_TARGET = 1024` (`M:app/services/h3_prompt_budget.py:1-9`, `:23`).

### A.7 Sliding windows and hard cuts (upstream)

**Per-window prompts** (`E:models/minimax_h3/prompt_enhancer.py:6`):
- Use `PW`, and "Keep all the H3 fields for one window together without empty lines, then insert one empty line before the next window's prompt."
- The engine's agent guide says the same: "use `PW` for sliding windows, with exactly one blank line between windows and none within" (`E:shared/deepy/prime_system_prompt.txt:29`).

**Window commands** go at the start of a window's paragraph:
- `[/duration=124]`, `[/duration=5s]` or `[/duration=20%]`, `[/overlap=18]`, `[/new_shot]` (`prompt_enhancer.py:8-14`);
- combinable: `[/duration=5s,/new_shot]` (`:16`);
- "WanGP removes these commands before sending the prompt to H3." (`:16`)

**Two kinds of cut:**
- "`[Shot 2] At MM:SS.mmm, ...` describes a model-directed cut **inside one H3 window**. Use `[/new_shot]` at the beginning of a later window when the boundary between two generated windows itself must be a hard cut." (`:18`)

**Each window starts over:**
- "Each window restarts at Shot 1 and time zero. Overlap is Picture 1; its end anchor is Picture 2." (`:36`)
- A window's end time is its `generated_seconds` in `wangp_validate`'s `window_plan` (`:36`; computed at `E:shared/mcp/preflight.py:83`).

### A.8 Continuation (continuing an existing clip)

**How the engine continues:**
- The continued frame is `<Picture 1>` and is not shown to the prompt writer. "If no description is headed `<Picture 1>`, then `<Picture 1>` is the last frame of the previous window, which you cannot see: continue directly from it without describing its content." (`E:models/minimax_h3/prompt_enhancer.py:269`)
- With `video_source`, the source's tail supplies the overlap frames (`E:wgp.py:7845-7867`).
- `[/new_shot]` drops the carried frames (`:7839-7840`).

**A complete upstream continuation prompt: NOT FOUND** (§F). Maestro's handling is in §B.2 and its example in §D.3.

---

## B. Enforcement

### B.1 The engine's own MCP server (upstream WanGP)

These are not in the brief's list, but they are the closest thing to an official enforcement API.

**Tools:**
- `wangp_model(model_type: str, view: Literal["schema", "definition", "defaults"] = "schema", property: str | None = None)` (`E:shared/mcp/server.py:1777`). Its description reads: "Return one model's compact schema, definition, or generation defaults. … repeat view='definition' with the property named in the suffix to retrieve its full value." (`:1778`)
- `wangp_validate(settings, media, process, parameters, detail: Literal["summary","full"])` (`E:shared/mcp/v2.py:863`). It returns a per-window `window_plan`: `generated_frames`, `generated_seconds`, `new_frames`, `new_shot`, `pictures` and `prompt` (`E:shared/mcp/preflight.py:83-91`). It also warns when the prompt and window counts differ.

**How an agent gets the rules:**
- For agents, the server swaps the agent text in under the canonical names. "help_detail "agent" serves deepy_infos / deepy_prompt_infos under the canonical names" (`server.py:563-571`).
- v2 `capabilities` points to it as `prompt_guidance` (`E:shared/mcp/v2.py:396-401`).
- The enhancer system prompts (keys containing `prompt_enhancer`) are listed as `other_declarations` and can be read by property (`server.py:558-559`, `:575-586`).

**Resource:** `wangp://guides/long-video` (`v2.py:1041-1043`) serves `E:shared/deepy/prime_guide.md` §"Long video…" (`:71-92`).

### B.2 Maestro Director Mode (public 2.6.0)

**MCP server and tools: NOT FOUND.**
- Searching for `mcp|modelcontextprotocol|fastmcp` finds nothing.
- `"tools"` and `"tool_choice"` appear only in a pass-through field allow-list (`M:app/services/llm_service.py:715-716`).

**Mechanism.** Maestro calls an LLM through `llm_service.generate(prompt, system_prompt, …, json_schema)` (`M:app/services/llm_service.py:2392-2407`), posting to `/v1/chat/completions` (`:2542`).
- With a JSON schema on the local llama-server, the grammar is enforced. Verbatim (`:2531-2535`):
  ```
  if json_schema is not None:
      if _provider == "local":
          payload["response_format"] = {"type": "json_object", "schema": json_schema}
      else:
          print(f"[LLM] json_schema requested but provider={_provider} — sending unconstrained (grammar is local llama-server only)")
  ```
- Thinking is turned off whenever a schema is used (`:2459-2461`).

**Passes** (`M:app/services/director/planners/short_film.py:7296-7302`):
- 0A story architecture;
- 0B character/voice [context];
- 1 screenplay (`INT./EXT. LOCATION - TIME`, `M:app/services/llm_guides/director/screenplay_writing_rules.md:1-5`);
- 1.5 table read (which locks the dialogue);
- 2 direction, one JSON object per shot.

**Schemas, verbatim** (`short_film.py`). `_SUBJECT_SCHEMA` (`:87-98`):
```
{"type":"object","properties":{"visual_description":{"type":"string"},"character_id":{"type":"string"},"speaker_name":{"type":"string"},"position_or_relation":{"type":"string"},"wardrobe":{"type":"string"}},"required":["visual_description"],"additionalProperties":False}
```
`_DIALOGUE_BEAT_SCHEMA` (`:100-112`):
```
{"type":"object","properties":{"speaker_id":{"type":"string"},"spoken_text":{"type":"string"},"language":{"type":"string"},"delivery":{"type":"string"},"physical_cue":{"type":"string"},"priority":{"type":"string"}},"required":["spoken_text"],"additionalProperties":False}
```
- `_CAMERA_PLAN_SCHEMA` (`:114-126`): `framing` (required), angle, movement, movement_intensity, lens_feel, reframing_notes.
- `_AUDIO_PLAN_SCHEMA` (`:128-140`): `mode` (required), ambience, `effects[]`, vocal_style, timing_anchor, `lip_sync_critical` (boolean).
- The shot object (`_SHOT_PROPERTIES`, `:146-176`) has:
  - title, duration_sec, scene_goal, narrative_role, scene_type;
  - continuity_strategy, continuity_group, story_scene_number, causal_handoff, persistent_story_state;
  - subjects_on_screen[], spatial_setup, environment, visual_style, lighting, mood;
  - action_beats[], dialogue_beats[], camera_plan, audio_plan;
  - ending_beat, closing_blocking;
  - image fields, video_prompt, multishot, keyframe_prompts[], window_prompts[].
- For H3, every field is required (`:10060-10080`).
- `_strengthen_native_schema` sets `window_prompts` `maxItems: 0` and makes every subject and dialogue-beat field required (`:10082-10109`).
- `continuity_strategy` is one of `{"independent","continuous","extend_previous"}` (`M:app/services/director/schema.py:279`).

**Pass 2 system prompt, key rules verbatim** (`short_film.py:9936-10009`):
- "Every video_prompt must stand alone, but it must also be economical: normally 180-450 words and never more than 650 words." (`:9941`)
- "CONVERSATION PACKING IS REQUIRED: … prefer one native clip … containing 2-4 alternating dialogue turns when their combined total is no more than {maximum_dialogue_words} words." (`:9956`)
- "DIALOGUE MUST NOT LIVE ONLY IN dialogue_beats. Every dialogue_beats[].spoken_text must also appear exactly once in the same shot's video_prompt as <d>[the beat's language] Exact words</d>, with the speaker ID/name, delivery, and physical cue outside the tag. If dialogue_beats is empty, explicitly state that no one speaks, mouths remain closed, and no muttering, gibberish, or speech-like vocalization occurs." (`:9960`)
- "Use video_prompt for every item and set window_prompts to []." (`:9940`)
- `maximum_dialogue_words = floor(maximum_seconds*3.0)` (`:9841-9856`).

**Guide appended to Pass 2** (`M:app/services/llm_guides/director/minimax_h3_shot_breakdown.md`):
- "Structure video_prompt with exactly these labeled sections: integrated_multimodal_description, overall_soundscape, non_diegetic_music." (`:37-38`)
- "Begin integrated_multimodal_description with [Shot 1] and no timestamp … Later cuts begin [Shot N] At MM:SS.mmm." (`:39-41`)
- "Give each speaking person a stable ID such as (S1) or (S2)." (`:42`)
- "When already numbered people speak or sing together, use a compound ID such as (S1,S2)." (`:43-44`)
- "use <d>[Language] Exact words</d>, where Language is the actual language of that line. Speaker identity, action, delivery, and voice are outside the dialogue tag." (`:45-48`)
- "For voiceover, use the exact phrase "says in an off-screen voiceover" and immediately state that the corresponding on-screen character's lips remain completely closed." (`:52-54`)
- `<scenetrans>`/`<cutoff>` wording as upstream (`:55-57`).
- "Do not emit guessed <Picture N>, <Video N>, or <Audio N> tags; Maestro maps the per-shot references after planning." (`:21-22`)

**The deterministic compiler.**
- After planning, the LLM's `video_prompt` is thrown away and rebuilt from the JSON fields for speaking shots, and for every shot when a story blueprint exists (`short_film.py:4199-4202`, `:4055-4058`). The H3 text is then written by `compile_h3_clip_plans` / `compile_h3_official_prompt` (`M:app/services/director/h3_dialogue.py`).
- **Silent shots** get: "No character speaks; all visible mouths remain closed, and no muttering, gibberish, speech-like vocalization, or background voice occurs." (`h3_dialogue.py:1755-1762`)
- **Alignment headers** (`h3_dialogue.py:2206-2224`):
  - i2va: `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`
  - fl2va: `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot {N}) aligns with the {d}-second mark of the target video.`
  - l2va: `… — <Picture 1> (from [Shot {N}]) aligns with the {d}-second mark …`
- **Speaker IDs** are project-wide, `(S{n})`, "once per Director project, not once per shot" (`h3_dialogue.py:1365-1417`).

**Validators** (`M:app/services/director/h3_dialogue.py`):
- **Dialogue-tag regexes** (`:31-35`):
  - `<\s*(/?)\s*d\s*>`: catches nested or unbalanced tags;
  - `<d>\s*\[([^\]\r\n]+)\]\s+(.+?)\s*</d>`: the canonical block; anything else gives "dialogue block N is not canonical".
- **`validate_h3_vocal_contract`** (`:348-396`) rejects:
  - nested or unbalanced tags;
  - a wrong block count;
  - words or speaker order that differ from `dialogue_beats`;
  - a silent prompt without `\bno (?:one|character) speaks\b`.
- **`validate_h3_prompt_contract`** (`:2403-2528`) rejects:
  - a field that does not appear exactly once, checked with `(?mi)^\s*{field}\s*:` ("expected one {field} field, found N");
  - fields out of order;
  - a base prompt whose visual field does not start with `[Shot 1]`;
  - wrapper words such as `OPENING CONTINUITY:`;
  - C1 control characters;
  - missing identity or world anchors;
  - a wrong mode header;
  - a Ref2VA summary that fails `^\[(?:reference generation|video editing|video continuation|keyframe completion|audio reuse|audio reference)(?:\s+\+\s+(?:...))*\]\s+\S`;
  - unmapped `<Picture/Video/Audio N>`;
  - retention lines that fail the mode regexes.
- **Word budget:** `max(1, floor(duration*3.0))` (`:547-584`).

**Repair loop:**
- **JSON:** one retry at temperature 0.3, then fall back through regex extraction and `json_repair`. The repair text (`M:app/services/director/planners/base.py:427-433`): "Your previous response was not valid JSON. Please output ONLY a JSON array of objects. No markdown fences, no explanation, no thinking tags. Just the raw JSON array starting with [ and ending with ].\n\nOriginal request:\n{user_prompt}"
- **Whole plan:** one repair, "H3 WHOLE-PLAN REPAIR - YOUR PREVIOUS PLAN WAS REJECTED: {issue_lines} … Never return a partial array, truncate a line, move dialogue to an unrelated visual beat, nest <d> tags, or exceed {3} spoken words per second in any shot." (`short_film.py:10465-10482`). The dialogue is then replaced from the locked manifest (`:10527-10543`).
- **Final failure:** `RuntimeError("… No video jobs were queued.")` (`:10514-10538`, `:10664-10669`), or `H3DialogueContractError` from preflight (`h3_dialogue.py:2641-2644`). In both cases the pipeline sets `status="failed"` and runs no GPU job (`M:app/services/director_pipeline.py:5906-5940`).

**What it sends to H3**, per clip (`M:app/services/director_pipeline.py:7912-7935`):
- `model_type`, `prompt` (clips joined by `"\n---CLIP_BOUNDARY---\n"`, `:7788`);
- `image_mode` 0, `multi_prompts_gen_type` 3, `image_prompt_type` (`""`, `"S"` or `"SE"`, `:7904-7909`);
- `num_inference_steps`, `guidance_scale`, `resolution`, `video_length`, `sliding_window_size`;
- `per_clip_frames`, `per_clip_prompt_modes`, `seed` −1.

**Its own extensions** of WanGP (the installed engine has none of them):
- Seamless mode adds `"minimax_h3_multi_window": True` and `"h3_window_prompts": [...]` (`:7747-7776`).
- The worker gives each clip `h3_window_prompts = [prompt]` (`M:app/launch.py:25980-25982`).

### B.3 HocusPocus

**NOT FOUND (not reachable).** What reading the server would take:
- read `app/models/h3_advanced/` (its H3 handler fork, cited in R14 as `app/models/h3_advanced/minimax_h3_handler.py:48`);
- read its prompt files, any MCP server, and its validators;
- fill every HocusPocus cell below.

---

## C. Upstream vs Maestro vs HocusPocus, rule by rule

| Rule | Upstream WanGP 18.05 | Maestro 2.6.0 | HocusPocus |
|---|---|---|---|
| **Base model** (FL2VA) fields | 3 fields, in order, `E:…/prompt_enhancer.py:252` | Same, validated by `M:…/director/h3_dialogue.py:2403-2425` | NOT CHECKED |
| **Ref2VA** fields | 6 sections, `prompt_enhancer.py:284` | Same, `M:app/models/minimax_h3/ref2va.py:92-99` | NOT CHECKED |
| **Shot 1** timing | "no timestamp" (`:254`) | Guide agrees (`shot_breakdown.md:39-41`), but the window compiler writes `[Shot 1] … From {start} to {end} seconds` (`M:app/services/h3_window_planner.py:575`) | NOT CHECKED |
| **Later cut** | `[Shot N] At MM:SS.mmm, …` (`:254`) | `[Shot N] At MM:SS.mmm, {transition or 'hard cut'} to {framing}; continue through MM:SS.mmm` (`h3_window_planner.py:582-586`) | NOT CHECKED |
| **Cut without a shot tag** | Not defined | `At MM:SS.mmm, without a cut, reframe to …` with no `[Shot N]` (`:576-580`) | NOT CHECKED |
| **Speech** | `(S1) <d>[Lang] …</d>` | Same, plus a canonical-block regex (`h3_dialogue.py:32-35`) | NOT CHECKED |
| **Speaker IDs** | Stable across the timeline (`:256`) | Director: project-wide (`h3_dialogue.py:1365-1417`). Studio Ref2VA: renumbered per clip (`M:app/services/h3_sequence_planner.py:1446-1450`) | NOT CHECKED |
| **Voiceover** | NOT FOUND | "says in an off-screen voiceover" with lips closed (`shot_breakdown.md:52-54`) | NOT CHECKED |
| **Silent shot** | NOT FOUND | Explicit silence sentence required (`h3_dialogue.py:1755-1762`) | NOT CHECKED |
| **`<scenetrans>` / `<cutoff>`** | Defined (`:256`) | Guide only; no code (`shot_breakdown.md:55-57`) | NOT CHECKED |
| **Words per second** in video | NOT FOUND | 2.8 target, 3.0 maximum (`M:app/services/dialogue_timing.py:6-7`) | NOT CHECKED |
| **Words per second** in audio | 2.6 (`dialogue.py:23`) | 2.8 (`M:app/models/minimax_h3/voice_audio.py:122-126`, per the grammar pass) | NOT CHECKED |
| **Prompt length** | Ref2VA `detailed_description` about 350–500 words (`:292`) | Director 180–450 words, ≤ 650 (`short_film.py:9941`); guide 450/480 tokens versus code 1024 (§A.6) | NOT CHECKED |
| **Window size** | 124–481, default 362; overlap ≤ 120 | 124–345; overlap ≤ 103 (`M:app/models/minimax_h3/minimax_h3_handler.py:74-82`) | NOT CHECKED |
| **Window prompts** | `PW` paragraphs and `[/…]` commands | No slash commands; prompts passed as an array, `h3_window_prompts` | NOT CHECKED |
| **Hard cut between windows** | `[/new_shot]` | Independent clips ("hard-cut mode", `h3_sequence_planner.py:1-7`) | NOT CHECKED |
| **fl2va header** | `<Picture 1> (from [Shot 1])` form (`:30`) | `Picture 1 (from Shot 1)`, without brackets (`h3_dialogue.py:2213-2218`) | NOT CHECKED |
| **Audio speakers** | 1–3 (A/B/D) | 1–2 (`voice_audio.py:80-81`, per the grammar pass) | NOT CHECKED |
| **Enforcement** | None for grammar; the media and window parts in code | Grammar JSON, then compiler, then validator, then one repair, then fail closed | NOT CHECKED |
| **MCP** | Yes: `wangp_model`, `wangp_validate` (§B.1) | NOT FOUND | NOT CHECKED |

---

## D. Five valid worked examples, verbatim from the sources

### D.1 A single shot (FL2VA, text only)

From `E:models/minimax_h3/prompt_enhancer.py:82-84`; also shipped as the agent template `E:shared/deepy/settings/gen_video/MiniMax H3 FL2VA Pruned PDD 8 Steps.json:9`.
```
integrated_multimodal_description: [Shot 1] At blue hour, a tired bicycle courier in a yellow raincoat pedals through a narrow rain-soaked market street. The camera tracks beside [the courier] at wheel height, then rises smoothly into a medium close-up as [the courier] stops beneath a flickering awning. Water runs from [the courier's] helmet while [the courier] catches [the courier's] breath, looks toward the closed train station, and says (S1) <d>[English] I missed it again.</d> Neon reflections ripple across the pavement and the shot holds on [the courier's] rueful smile.
overall_soundscape: Steady rain on canvas and metal, bicycle-chain clicks, wet tires hissing over stone, distant traffic, and the courier's breath settling after the stop.
non_diegetic_music: N/A
```

### D.2 A two-speaker dialogue

- **Upstream video example with `(S1)` and `(S2)`: NOT FOUND.**
- **Video, from Maestro's H3 guide** (`M:app/services/llm_guides/enhance/minimax_h3_video.md:183-187`). It has blank lines between the fields, so send it with `FG`, not `PW` (§A.7).
  ```
  integrated_multimodal_description: [Shot 1] Live-action workplace comedy, a medium two-shot holds on two coworkers at adjacent desks as the camera slowly pushes in. The relaxed younger coworker with a warm, conversational voice (S1) turns from [the coworker's] monitor and says: <d>[English] It makes videos and music right on your computer.</d> The rigid older coworker with a clipped, intense voice (S2) leans closer and replies: <d>[English] Good. The cloud is a security weakness.</d> They exchange a deadpan look and remain silent with their mouths closed through the final beat.

  overall_soundscape: Low office room tone, distant keyboard taps, and a quiet ventilation hum continue beneath the exchange.

  non_diegetic_music: N/A
  ```
- **Audio-only model, upstream** (`E:models/minimax_h3/prompt_enhancer.py:378-385`):
  ```
  Speaker 1:
  [English, young woman with a clear low voice, tense, clipped delivery] The signal disappeared at the exact moment the door opened.
  Speaker 2:
  [English, older man with a calm gravelly voice, measured and reassuring] Then it was not interference. It was waiting for us.
  Speaker 1:
  [English, lowering [the speaker's] voice to an uneasy whisper] You say that as if it makes this better.
  Speaker 2:
  [English, firm, quiet, close to the microphone] No. I say it because now we know when to run.
  ```

### D.3 A continue of an existing clip

- **Upstream: NOT FOUND** as a complete prompt. The rules are in §A.8.
- **From Maestro: window 2 of a 14-window native Ref2VA continuation** (`M:docs/prompts/blaine-maestro-reference-manual.txt:2`; one window per line, `M:docs/prompts/blaine-maestro-tutorial-script.md:7`).
- **What Maestro adds before H3 sees it** (`M:app/models/minimax_h3/ref2va.py:1288-1320`):
  - The prompt's Picture labels shift up by 1.
  - It prepends "<Picture 1> is the exact final frame carried from the preceding window. Use it only as the opening composition and motion boundary; continue forward without restaging it or treating it as a new identity reference."
  - It adds the retention `<Picture 1>: exact opening-boundary continuity`.
```
subject_definitions: <Subject 1> is [Character 1] from <Picture 1>, preserving facial identity and hair. <Audio 1> is the voice-timbre reference for <Subject 1> (S1), guiding emotion and delivery. summary: [reference generation + audio reference] A single locked-camera segment of [Character 1's] tutorial. retention_analysis: <Subject 1>: partially_preserved - preserve face and hair; use the described outfit and setting. <Audio 1>: reference - preserve voice identity for the new scripted line. detailed_description: Photorealistic recording, natural skin texture, soft even studio light. [Shot 1] <Subject 1> sits centered against a matte warm-gray wall in a plain charcoal crewneck, chest-up with full head, shoulders and crop margin visible. Hands remain below frame. The eye-level camera, framing, focus and exposure stay fixed in one uninterrupted shot. From 0.00 to 0.25 seconds, [the subject] holds eye contact with relaxed, closed lips. From 0.25 to approximately 11.32 seconds, <Subject 1> (S1) says the following once, with clear conversational delivery at about 2.8 words per second in the voice referenced from <Audio 1>, <d>[English] In Studio, choose video, image, or audio. For this walkthrough, let's start by creating a video. Choose a model for your workflow. I'm using MiniMax H3 Reference with my saved character.</d> [The subject's] lip movements synchronize to these exact words. From 11.32 to 13.625 seconds, [the subject] remains silent with lips closed, makes a small natural blink and holds the same posture. The background and lighting stay unchanged. overall_soundscape: Quiet, steady studio room tone. The pauses contain only room tone. non_diegetic_music: N/A
```
**Caution.** All six fields sit on one line. Maestro's own Director validator anchors fields at line starts (`(?mi)^\s*{field}\s*:`, `M:…/director/h3_dialogue.py:2420-2422`), so it would reject this form. Upstream's examples put each field on its own line.

### D.4 A scene change inside one clip (model-directed cuts in one window)

From `E:models/minimax_h3/prompt_enhancer.py:99-101`.
```
integrated_multimodal_description: [Shot 1] A red fox runs across a snowy ridge at sunrise as a long-lens camera pans with it, powder spraying from every stride. [Shot 2] At 00:04.000, cut to a wide aerial view as the fox descends into a pine valley, its trail drawing a curved line through untouched snow. [Shot 3] At 00:07.500, cut to ground level beside a frozen stream; the fox slows, listens, and looks directly past the camera while drifting snow catches the orange backlight.
overall_soundscape: Fast paw impacts in powder, cold wind across the ridge, distant crows, snow falling from pine branches, and the fox's quiet breathing near the stream.
non_diegetic_music: Low sustained cellos with a restrained frame-drum pulse, opening into a single bright horn note in the final shot.
```
For a hard cut *between* windows, the next paragraph starts with `[/new_shot]` (`prompt_enhancer.py:14`, `:18`). A complete multi-window example with commands: **NOT FOUND**.

### D.5 Ref2VA with an identity picture

From `E:models/minimax_h3/prompt_enhancer.py:192-201`. Send it with `video_prompt_type "I"` and `image_refs`; the template is `E:shared/deepy/settings/gen_video_with_refs/MiniMax H3 Ref2VA Pruned PDD 8 Steps.json:9`.
```
subject_definitions:
<Subject 1> is the violinist from <Picture 1>, preserving [the violinist's] identity, facial features, dark braided hair, burgundy concert dress, and antique violin.
summary:
[reference generation] Place <Subject 1> in a new dawn performance on a misty rooftop while preserving [the violinist's] recognizable appearance and instrument.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity, face, hair, burgundy dress, and antique violin are retained; the rooftop setting and performance are new.
detailed_description:
The target video is a cinematic single-shot rooftop performance at dawn with cool mist and soft amber rim light. [Shot 1] <Subject 1> stands near the roof edge, framed from the waist up against a waking skyline. [The violinist] raises the referenced violin naturally to [the violinist's] shoulder and begins an energetic passage, [the violinist's] bowing, fingering, posture, dress movement, and breathing remaining physically coherent. The camera makes a slow semicircle around [the violinist], widening as the mist parts and ending with [the violinist] lowering the bow after the final note.
overall_soundscape: Light rooftop wind, distant morning traffic, fabric movement, breathing, and close natural violin performance.
non_diegetic_music: N/A
```

---

## E. Validator checklist

**How the "Published" column reads:**
- **AG**: in the agent help the engine serves (`deepy_prompt_infos`/`deepy_infos`, through `wangp_model(view="definition", property="prompt_infos")`).
- **UI**: in `prompt_infos` (UI help).
- **NUM**: a numeric definition field.
- **SYS**: only inside an enhancer system prompt (an internal declaration, readable by property).
- **CODE**: enforced by engine code; the Hub can rely on the engine refusing it.
- **—**: not in the engine (Maestro only).

| # | Testable rule | Source | Published |
|---|---|---|---|
| **FL2VA** | | | |
| 1 | FL2VA text has exactly the fields `integrated_multimodal_description:`, `overall_soundscape:`, `non_diegetic_music:`, once each, in that order | `E:…/prompt_enhancer.py:252`, `:25-28` | AG UI SYS |
| 2 | No blank line inside a window's fields | `:25`, `:6` | AG UI |
| **Ref2VA** | | | |
| 3 | Ref2VA has the six sections in order, once each | `:284`, `:108-114` | AG UI SYS |
| 4 | Ref2VA `summary` matches `^\[(tag)( \+ tag)*\] \S`, with tags from the six names | `:288`, `:110`; regex `M:…/h3_dialogue.py` (§B.2) | AG UI SYS |
| 5 | Each `retention_analysis` line matches `<Label> …: mode - …`, with the mode in the visual or audio set | `:290`, `:111` | AG UI SYS |
| 6 | Every `<Picture/Video/Audio N>` used maps to a supplied medium, and numbering per type starts at 1 with no gaps | `:286`; `E:…/text_encoder.py:124-155` | AG SYS, CODE (presentation) |
| 7 | Picture order is start or continued frame, then end image, then injected frames by time, then references; it restarts each window | `:120`; `E:…/pipeline.py:941-996` | AG, CODE |
| 8 | A speaking Ref2VA subject is written `<Subject N> (Sx)` | `:294` | SYS (UI example `:182`) |
| 9 | Ref2VA `detailed_description` is about 350–500 words for reference generation | `:292` | SYS UI |
| **Shots** | | | |
| 10 | The first shot token is `[Shot 1]` with no `At` time | `:254`, `:32` | AG UI SYS |
| 11 | Later shots match `\[Shot (\d+)\] At (\d\d):(\d\d)\.(\d{3}),`, with N increasing by 1, times strictly increasing and within the window length | `:254` | AG UI SYS |
| **Speech** | | | |
| 12 | Every speech block matches `<d>\[[^\]\r\n]+\]\s+.+?</d>`, with no nesting and tags balanced | `:256`; regexes `M:…/h3_dialogue.py:31-35` | AG UI SYS (regex is Maestro's) |
| 13 | Each `<d>` is preceded by a speaker ID `\(S\d+(,S\d+)*\)`, stable per speaker for the whole timeline | `:256`; compound form `M:…/shot_breakdown.md:43-44` | AG SYS |
| 14 | Only spoken or sung words inside `<d>`; delivery and identity outside | `:256`; `M:…/shot_breakdown.md:45-48` | SYS |
| 15 | `[Language]` is the spoken language; the description is in English | `:252` | AG SYS |
| 16 | `<scenetrans>` appears in pairs, around a cut; `<cutoff>` appears only at the end | `:256` | AG UI SYS |
| **Sound fields** | | | |
| 17 | `overall_soundscape` repeats no `<d>` text | `:258` | SYS UI |
| 18 | `non_diegetic_music` is `N/A` when no score is requested | `:258` | AG UI SYS |
| **Anchors and soundtrack** | | | |
| 19 | With a start image, the first line is `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` | `:30`, `:275` | AG SYS |
| 20 | Soundtrack mode (`A`/`K`/`AS`/`KS`): no `<Audio N>` for the kept track, no mention of it, and lip-sync wording present | `:34`, `:116`; `E:…/pipeline.py:1029` | AG, CODE (label) |
| **Windows and prompt lines** | | | |
| 21 | Under `PW`, exactly one blank line between windows, and the paragraph count equals the planned windows (`wangp_validate` warns) | `:6`; `E:…/prompt_parser.py:62-78`; `E:shared/mcp/preflight.py:86-91` | AG UI, CODE (warning) |
| 22 | Each window restarts at `[Shot 1]` at time 0 | `:36` | AG UI |
| 23 | Window commands only from `{duration, overlap, new_shot, no_end_image, loras_mult}`, with `/duration` a positive integer, `Ns` or `N%` | `E:shared/utils/frame_scheduler.py:8`, `:54-67`, `:144-146` | CODE |
| 24 | H3 overlap is `1 + 17k`; `/new_shot` takes no value | `frame_scheduler.py:105-131` | CODE, NUM |
| 25 | No prompt line starts with `!`; no `{…}` except in `Speaker N {…}:` | `prompt_parser.py:7`, `:224`, `:298-304` | CODE |
| 26 | Window frames are `17k + 5`, within 124–481 (control ≤ 362) | `E:…/minimax_h3_handler.py:581-583`, `:796-797`, `:546-547` | NUM, CODE |
| **Audio-only model** | | | |
| 27 | One turn per `Speaker N:` block, and each block has text outside `[ ]` | `E:…/dialogue.py:44`, `:130-131` | AG, CODE |
| 28 | Each turn's first bracket item names a language from `_LANGUAGES` | `dialogue.py:46-62`, `:101-110` | CODE (silent fallback); SYS |
| 29 | Turn length is ≤ 45 s at 2.6 words/s; total is 4–300 s | `dialogue.py:17-23`, `:148-151`; handler `:874-880` | CODE, NUM (`duration_slider`) |
| 30 | Audio scripts contain no `<d>`, XML or section names, and no window commands | `prompt_enhancer.py:349`; `E:wgp.py:1093-1094` | SYS, CODE (commands) |
| **Maestro only** | | | |
| 31 | Video speech is ≤ 3.0 words per second of shot time | `M:app/services/dialogue_timing.py:7` | — |
| 32 | A silent shot states that no one speaks (`\bno (?:one|character) speaks\b`) | `M:…/h3_dialogue.py:1755-1762` | — |
| 33 | A voiceover uses "says in an off-screen voiceover" with lips closed | `M:…/shot_breakdown.md:52-54` | — |
| **Model-specific** | | | |
| 34 | Viggle: prompt text is ignored, so do not send one | `E:…/minimax_h3_handler.py:504` | AG UI |

**For the Hub.**
- **Read the rules from the engine:** rules 1–3, 10–11, 15–16, 18–22, 27 and 34 can be read at run time through `wangp_model(view="definition", property="prompt_infos")`.
- **Let the engine check:** `wangp_validate` covers rules 21 and 23–26, and a submit fails on them.
- **Hub validator, layer one:** the regexes for rules 4, 5 and 11–13 come from Maestro's code, not the engine. They are the minimal validator.

---

## F. Open questions and NOT FOUND

**NOT FOUND:**
- **Hard to find in the engine:**
  - any engine parsing of section names, `[Shot N]`, `<d>` or `(Sx)`;
  - any H3 prompt token limit;
  - any word-per-second rule for video speech.
- **Missing upstream examples:**
  - an upstream video example with two speakers;
  - a continuation (`video_source`) prompt;
  - a multi-window `PW` prompt with `[/…]` commands;
  - an end-image or injected-frame alignment line other than the 0.00 s start line;
  - any `<scenetrans>`/`<cutoff>` example;
  - the format of a Ref2VA keyframe `<Picture N>` entry in `subject_definitions`.
- **Not in the clone:** the official MiniMax guides credited at `E:…/prompt_enhancer.py:104` and `:245` (external URLs).
- **Not in Maestro:** an MCP server or tool definitions; any validator for `<scenetrans>`/`<cutoff>`; a complete Director-compiled prompt in tests or fixtures (tests assert prefixes only, e.g. `M:tests/test_h3_director_dialogue.py:546-563`).
- **HocusPocus:** everything.

**Contradictions to settle before building the Hub's assistant:**
1. **Blank lines between Ref2VA sections.** The UI skeleton and the voice example use them (`E:…/prompt_enhancer.py:136-156`, `:224-238`), but `PW`/`PG` split on them (`E:…/prompt_parser.py:48-59`). Use single newlines.
2. **The image enhancer's blank line.** `FL2VA_IMAGE_SYSTEM_PROMPT` asks for a blank line after the alignment lines (`:275`). Enhancer output strips blank lines in P modes (`E:wgp.py:6761-6762`), but a hand-written `PW` prompt would split.
3. **Maestro's Shot 1.** Maestro's window compiler gives `[Shot 1]` a time range (`M:…/h3_window_planner.py:575`), against "Shot 1 has no timestamp" (upstream `:32`; Maestro's own guide `shot_breakdown.md:39`).
4. **Prompt length.** Maestro's 450/480-token "real limit" (guide) and its 1024 "not a gate" (code) disagree. Upstream says nothing (§A.6).
5. **Shipped templates break the soundtrack rule.** The engine's "With Sound" templates omit the lip-sync wording, and the Ref2VA one says "The supplied soundtrack." (`E:shared/deepy/settings/gen_video_with_speech/…`), against "without mentioning a supplied audio track" (`E:…/prompt_enhancer.py:34`, `:116`).
6. **Shipped defaults break the field rule.** Some shipped defaults lack required fields, e.g. `E:defaults/minimax_h3_fl2va_pdd.json:19` has no `non_diegetic_music` (per the upstream pass).

**Open questions:**
1. Is the installed engine exactly `af2ed29`? If not, the `E:` line numbers need a re-read. Linking the server would settle it.
2. Is the server's Maestro 2.6.0 the same as GitHub `Blizaine/Maestro` `31d7396`?
3. HocusPocus: does it have an MCP server, and does it keep the fork's Omni manifest (`minimax_h3_references`) prompt rules?
4. Should the Hub's assistant use `PW` with `[/…]` commands (upstream) or one clip per prompt (Maestro Director)? This decides rules 21–24.
