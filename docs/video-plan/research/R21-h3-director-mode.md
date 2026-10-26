# R21 — How Director Mode makes an LLM's MiniMax H3 prompts comply, and how the Hub gets the same

Status: 2026-10-15. Read-only source analysis; nothing installed, run or written
outside this file. For the Hub's architect, before a Director stage is specified.

**Sources (copies in this workspace, not the server install; the server copy is the same version):**

| Code | Tree | Version | License file |
|---|---|---|---|
| `UP:` | upstream WanGP `af2ed29` | 18.05 | `LICENSE.txt` (WanGP Community License 2.0) |
| `MA:` | Maestro | 2.6.0 (`VERSION`) | `LICENSE` ("Maestro License Notice"), `app/LICENSE.txt`, `THIRD_PARTY_NOTICES.md` |
| `HP:` | HocusPocus | 0.10.0 (`VERSION`) | `LICENSE` (same notice), `app/LICENSE.txt`, `app/licenses/wangp-1272.txt`, `wangp-1300.txt` |
| `HUB:` | the Hub | `0c904a1` | — |

Every claim cites `prefix:path:line`. "NOT FOUND" means searched and absent.

---

## 0. The finding in one paragraph

Director Mode's compliance does not come from telling the LLM the rules better. It comes from **never letting the
LLM write the H3 prompt**. The LLM fills a model-neutral *shot plan* (a JSON object with subjects, action beats,
camera, dialogue lines, ending, audio mode), under a grammar that makes malformed output impossible; a
**deterministic compiler** turns that plan into H3's documented field structure; a **validator** refuses the result
before any GPU work; the **clip length is computed from the dialogue**, not asked of the LLM; and an optional
LLM "polish" pass is accepted only if it survives the same validator, else the deterministic draft ships. The
system prompt still carries craft guidance, but nothing load-bearing depends on the LLM obeying it. The Hub today
does the opposite: a free-text `draft` and an 845-word paragraph of rules (`HUB:docs/video-plan/system-prompt-video-paragraph.md`),
with no check between the LLM and the engine. That is why it drifts and Director Mode does not.

---

## 1. Ground truth: what the engine parses (upstream 18.05)

### 1.1 Two dialects, two entry points

**A. Context-IR, for video models.** The prompt is a few labelled lines, in a fixed order, no blank lines inside:

- FL2VA (First / Last and its presets): `integrated_multimodal_description:`, `overall_soundscape:`,
  `non_diegetic_music:` (`UP:models/minimax_h3/prompt_enhancer.py:23-32`; example `:82-84`).
- Ref2VA (identities): six fields `subject_definitions:`, `summary:`, `retention_analysis:`,
  `detailed_description:`, `overall_soundscape:`, `non_diegetic_music:` (`:108-121`; example `:236`).
- Inside the description: `[Shot 1]` first with no timestamp, later cuts `[Shot N] At MM:SS.mmm, ...`; stable
  speaker ids `(S1)`; exact speech only inside `<d>[Language] words</d>`; `<scenetrans>` at both sides of a line
  crossing a cut; `<cutoff>` for a line the last frame interrupts; visible lettering quoted separately; ambience in
  `overall_soundscape`, audience-only score in `non_diegetic_music`, `N/A` when none (`:32`, `:61`, `:118`, `:256`).
- Reference labels: `<Subject N>` reusable person/object/setting, `<Picture N>` concrete image, `<Video N>`,
  `<Audio N>`; each numbered independently; start/end images come before general references in the Picture
  numbering (`:116`). Frame anchors are declared with a fixed alignment sentence: `For the target video, at 0.00
  seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` (`:30`).
- Lip-sync wording when a soundtrack is kept (`A`/`K` on FL2VA, `AS`/`KS` on Ref2VA): "speaking with natural lip
  movements synchronized", name the speaker, no transcript, no `<Audio N>` label for the track (`:34`, `:116`).

**B. `Speaker N:` scripts, for the audio-only dialogue model only.** One turn per `Speaker N:` block, directions in
`[square brackets]`, not spoken (`UP:models/minimax_h3/dialogue.py:30-41`; header regex `:44`, direction regex
`:45`). The *engine* compiles each turn into a six-section Ref2VA prompt itself (`:176-196`) and joins the turns.
So for speech the compiler already exists in the engine; for video it does not. The Hub's Stage 12 uses path B.

### 1.2 What the engine checks, and what it does not

- It checks prompt-unit structure: the prompt is split by `multi_prompts_gen_type` (`FG` = one unit; `P…` =
  paragraphs split on blank lines; `PW` = one paragraph per sliding window), refuses an empty prompt, refuses a
  multi-unit prompt on a single-task submission, and checks window boundaries
  (`UP:wgp.py:1073-1086`; `UP:shared/utils/prompt_parser.py:35-60`). The Hub sends `FG`
  (`HUB:hub/worker/adapters/tasks.py`, the clip task), so its whole prompt is one unit.
- It parses window commands at a paragraph's start: `[/duration=124]`, `[/duration=5s]`, `[/duration=20%]`,
  `[/overlap=18]` (17k+1), `[/new_shot]` (= `/overlap=0`, a hard cut); it removes them before the model sees the
  text (`UP:models/minimax_h3/prompt_enhancer.py:4-22`; errors in `UP:shared/utils/frame_scheduler.py:102-118`).
- **It does not check Context-IR.** Field order, `<d>` tags, speaker ids, `[Shot N]` times: any string is accepted
  and sent to the model. Compliance is the client's job. NOT FOUND: any Context-IR validator in `wgp.py`,
  `shared/api.py` or the H3 handler.

### 1.3 Rules the engine publishes in machine-readable form

Per model definition, read by the engine's own agent ("Deepy", `UP:shared/deepy/`):

| Field | Holds | Where |
|---|---|---|
| `deepy_prompt_infos` | the prompt-writing rules of §1.1 for that family | FL2VA `UP:models/minimax_h3/minimax_h3_handler.py:794-795`; Ref2VA `:717-718`; Control `:541-542`; audio-only `:418` (`Speaker N:` rules) |
| `deepy_infos` | settings guidance (letters, duration cap, PDD 8 steps, VDN) | `:417`, `:838-853` |
| `audio_prompt_type_sources` | letters and labels per family | `:769-785` (Ref2VA), `:821-833` (FL2VA) |
| `image_ref_choices` / `video_prompt_type` letters | identities "I", start/end frames | handler definition blocks |
| `sliding_window_defaults`, `window_min`/`window_max`, frame lattice 17k+5, fps 24 | lengths | `:577-583`, `:796-797`, `:719` |
| `duration_slider`, `audio_reference_max_total_duration` | speech caps | `:368-378` |
| `preserve_empty_prompt_lines` | blank lines kept in the prompt | `:357` |

The Hub's `--dump-engine` capture already carries the definitions; these fields can be read at run time instead of
hardcoded (Stage 9's `READS`/`GAPS` contract test governs which fields are read).

---

## 2. The Director Mode mechanism (HocusPocus; Maestro shares the package)

Both apps carry `app/services/director/`, declared as four layers: skill planners → shared schema → render
adapters → validators (`HP:app/services/director/__init__.py:1-6`). Maestro 2.6.0 has the same package
(`MA:app/services/director/`, `h3_dialogue.py` 2645 lines); HocusPocus split the H3 pieces into smaller modules.
**Neither uses MCP for Director Mode**: it is an in-process pipeline calling `llm_service.generate`
(`MA:app/services/director_pipeline.py:6105-6180`). NOT FOUND: any MCP server or tool list in either tree's
Director path (`grep -ri mcp` finds only UI capability names in HocusPocus's `ui/src/features/agent/*`).

### Gate 1 — The LLM fills a schema, not a prompt

- The unit is `ShotPlan` (`HP:app/services/director/schema.py:261-305`): `scene_goal`, `subjects_on_screen`
  (`SubjectRef` :123-158: `visual_description`, `character_id`, `position_or_relation`, `wardrobe`,
  `speaker_name`), `spatial_setup`, `environment`, `visual_style`, `lighting`, `mood`, `action_beats[]`,
  `camera_plan` (`CameraPlan` :190-221: `framing`, `angle`, `movement`, `movement_intensity`, `lens_feel`),
  `audio_plan` (`AudioPlan` :223-251: `mode` ∈ generated_audio | audio_driven | dialogue_driven | music_driven |
  ambient_only, `ambience`, `effects[]`, `timing_anchor`, `lip_sync_critical`), `dialogue_beats[]`
  (`DialogueBeat` :161-188: `spoken_text`, `speaker_id`, `delivery`, `physical_cue`), `ending_beat`,
  `continuity_strategy` ∈ independent | continuous | extend_previous (:259), optional `video_prompt`,
  `window_prompts[]` for scenes over 20 s (:295-296), `duration_sec`.
- The planner asks for a JSON array of these and passes a **JSON Schema** that the local llama-server turns into a
  grammar (`HP:app/services/director/planners/short_film.py:74-160`, the per-field schemas with
  `additionalProperties: False`). The call (`HP:…/planners/base.py:72-237`): grammar on the first attempt when
  thinking is off; thinking **off** for Qwen (runaway reasoning observed), on for Gemma; `frequency_penalty 0.3`,
  `presence_penalty 0.1` because structured JSON repeats otherwise (:90-100); on a parse failure one repair
  attempt with a fix prompt *and* a hard grammar, temperature 0.3, thinking forced off (:172-208); a server that
  rejects grammars degrades to the plain call (:139-152). After two failures the plan is empty, never garbage.
- The schema's own output rule for long scenes: "Scenes 20s or under: write video_prompt, leave window_prompts
  as []. Scenes over 20s: write window_prompts … Each window must briefly re-establish ongoing state"
  (`HP:…/planners/short_film.py:3261-3269`).

### Gate 2 — A deterministic compiler writes the H3 prompt

- `format_minimax_h3_prompt(plan, prompt, reference_mode, …)` (`HP:app/services/director/minimax_h3_prompting.py:231-298`)
  is "the single boundary where those plans become the structured FL2VA/Ref2VA prompts … Keeping the adapter
  deterministic means [every workflow] speak[s] the same dialect even when an LLM prompt-polish pass is
  disabled" (:1-8). It builds:
  - the body: `Visible subjects: (S1) …; (S2) …`, `Environment: …`, `Visual treatment: …`, `Lighting: …`,
    `Chronological action: …`, one sentence per dialogue beat `(S1) Name says <d>[Language] words</d>.`, the
    camera sentence, `The shot ends on …` (:159-196; dialogue :141-156; camera :117-138);
  - the fields: FL2VA → alignment sentence (when a first frame is given, :20-23) + `integrated_multimodal_description:`
    + `overall_soundscape:` + `non_diegetic_music:` (:278-298); Ref2VA → the six fields with
    `subject_definitions` from the subjects and a fixed `retention_analysis` (:256-276).
  - Field names come from one owner, `h3_prompt_policy.CONTEXT_IR_FIELDS` / `REF2VA_FIELDS`
    (`HP:app/services/h3_prompt_policy.py:11-23`); the `<d>` block from one function `tagged_dialogue`
    (:36-38); the language from `infer_h3_spoken_language` (`HP:app/models/minimax_h3/spoken_language.py`).
- The fuller compiler, `compile_h3_official_prompt` (`HP:…/director/h3_dialogue.py:1637-1807`), adds: a **stable
  speaker registry** across all shots so `(S1)` means the same person in every clip (`:1107-1150`, used at
  :1977-1990); Ref2VA `<Subject N>` definitions and their insertion at the subject's first mention
  (`:1511-1565`); the alignment header per mode: i2va "Picture 1 at 0.00", fl2va "Picture 1 at 0.00, Picture 2 at
  {duration}", l2va "Picture 1 at the end" (`:1567-1593`); dialogue placement that **replaces `<d>` blocks as whole
  units** rather than string-replacing words, which "originally split sentences and produced gibberish"
  (`:504-515`, `:1182-1302`).
- **Idempotence:** an already-structured prompt is recognised (`is_structured_h3_prompt`, :39-47) and passed
  through, so a user's edit of the visible prompt is not rewritten; a changed compiled prompt becomes the new
  source (`:1998-2008`). The planner's words are kept beside the compiled text as provenance
  (`_director_h3_source_prompt`, `_director_h3_compiled_prompt`, :334-341).

### Gate 3 — A validator refuses before the GPU

`validate_h3_prompt_contract` (`HP:…/director/h3_dialogue.py:1809-1975`), run on every clip immediately before
queuing (`compile_h3_clip_plans`, :1977-2063; Maestro's `_preflight_h3_director_prompts`,
`MA:app/services/director_pipeline.py:7073-7110`). Any error raises `H3DialogueContractError` naming the shot,
and nothing is generated. It checks:
- each field present exactly once and in order; no field of the other family (`h3_field_structure_errors`,
  `HP:app/services/h3_prompt_policy.py:41-55`; :1819-1826);
- every `<d>` block canonical `<d>[Language] words</d>`, balanced, and **the words and order equal the plan's
  `dialogue_beats`** (`validate_h3_vocal_contract`, :465-502);
- `audio_plan` consistency: exact dialogue requires `mode=dialogue_driven`, `timing_anchor=audio`,
  `lip_sync_critical=true`; a silent shot must not claim a vocal anchor (:1838-1880);
- no unstructured vocal cues left in the visual field or soundscape ("still contains vocal material") (:1881-1900);
- word budget: 2.1 words/second per shot, violations listed per shot (`h3_dialogue_budget_violations`, :652-690).

### Gate 4 — Length comes from the dialogue, not from the LLM

`HP:app/services/minimax_h3_duration.py`: speech time = syllables × 0.22 s (:37, :81-99, Castilian-aware) +
0.12 s per comma, 0.18 s per sentence end, 0.32 s per ellipsis, 0.15 s between lines, 0.35 s edge room
(:120-156). `apply_h3_dialogue_duration` rounds up to the 17n+5 lattice, clamps to the model's min/max read from
the definition (`frames_minimum`, `frames_maximum`, `frame_alignment_modulus/remainder`, :382-448) and, over the
maximum, refuses with "Split the dialogue across multiple clips; it will not be truncated" (:451-457). A
**vocal timeline** then assigns every second to a line or to closed-mouth silence (:159-304) and is kept as
metadata, not injected as prose, because "feeding long silence instructions back to H3 can itself elicit speech"
(:333-335).

### Gate 5 — LLM polish is optional and guarded

When an LLM is asked to improve the prose, its answer is accepted only if it keeps every `<d>` line verbatim,
keeps the structure, keeps the reference contract, stays within length bounds; otherwise the deterministic draft
is used (`_h3_validated_candidate`, `HP:app/services/director/h3_story_contracts.py:106-140`). The audio fields are
never taken from the polish (`_h3_preserve_audio_contract`, :143-153).

### Craft guidance still exists, but it is not load-bearing

`writing_contract` / `sound_contract` (`HP:app/services/h3_prompt_policy.py:76-105`) and Maestro's
`director_writing_contract` (`MA:app/services/director/writing_contract.py:8-31`) are prose rules given to the
planner: stable speaker ids in first-vocal-event order, only words and `[Language]` inside `<d>`, budget speech to
the real duration, a shot's ending state is the next continuous shot's opening state, a cut must not replay an
impact. They raise the hit rate; Gates 2–4 guarantee the floor.

### Continuation and scene changes

- Continuity is a plan field (`continuity_strategy`), not prompt wording. "continuous"/"extend_previous" makes the
  next shot's image source the previous output (`HP:…/planners/short_film.py:1533-1536`) and the compiler emits the
  i2va alignment header for it. The extend validator flags reset language ("establishing shot", "we open on")
  (`HP:…/validators/prompt_validator.py:166-177`).
- A scene change **inside one clip** is `[Shot N] At MM:SS.mmm` in the description (model-directed cut,
  `UP:…/prompt_enhancer.py:32`); a hard cut **between windows** is `[/new_shot]` at a window's start (`:19-21`).
  Director's window prompts carry the "re-establish ongoing state" rule (§Gate 1).

### Where Maestro and HocusPocus differ

Same schema, planners, speaker registry, compile and validate. HocusPocus 0.10.0 moved the dialect adapter
(`minimax_h3_prompting.py`), the duration contract (`minimax_h3_duration.py`) and the field policy
(`h3_prompt_policy.py`) into their own modules and added `h3_story_contracts.py` (the guarded polish); Maestro
2.6.0 keeps more inside `h3_dialogue.py` and has `writing_contract.py`, `vocal_activity.py`,
`reference_inputs.py`, `long_form_story.py`. The Ref2VA reference manifest in Maestro keeps the ordered
list so `<Picture N>`/`<Audio N>` numbers match the order shown on screen (`MA:app/services/director_pipeline.py:2439-2470`).
No rule of §1 differs between them.

---

## 3. Why the Hub's assistant drifts

- `generate_image` renders `screen.draft(ctx)`, a free string, as `prompt` (`HUB:hub/modules/generate_image/tools.py:50-78`).
- Every H3 rule the assistant must obey lives in the Open WebUI paragraph (845 words) and in the model's
  attention. Nothing in the Hub reads the draft for structure, dialogue, speaker ids or length.
- The engine accepts any string (§1.2), so a drifted prompt is not refused; it is rendered badly.
- The clip's length is the setting (the clip's seconds, set by hand), unrelated to the words spoken.

A free prompt through Ollama/ComfyUI and the Hub's draft are the same design.

---

## 4. The same mechanism in the Hub (the design; a Stage 13 spec follows this)

### 4.1 The lever the Hub has

The Hub cannot run its own LLM calls (invariant: the assistant is Open WebUI's; the Hub fetches nothing). But
Open WebUI's native tool calling passes each tool's **JSON Schema** to the model backend, and llama.cpp enforces
tool-call arguments as a grammar. So the Hub's **tool argument schema is Gate 1**, free. Everything else
(Gates 2–4) is plain code in the Hub, where it already belongs: Generate builds the engine task from the press.

### 4.2 Shape

1. **A structured shot on the press.** `set_generate_image_settings` gains a `shot` argument (an object) beside
   `draft`. Its schema is a Hub-sized `ShotPlan`: `subjects[]` {`name` (a character or a description),
   `wardrobe?`, `position?`}, `where`, `light?`, `style?`, `action[]`, `camera` {`framing`, `movement?`},
   `lines[]` {`speaker` (a subject name), `words`, `language?`}, `ending?`, `sound?` {`ambience?`, `music?`}.
   `additionalProperties: false`, `required` minimal (`subjects`, `action`, `camera`). The tool description stays a
   label (invariant 6). The storyboard's `put_cell` gets the same object in place of free clip text.
2. **The compiler** (`hub/modules/generate_image/h3prompt.py`, ≤300 lines, pure functions): shot → Context-IR for
   the model's family, read from the catalog entry: FL2VA (3 fields, alignment sentence when box 1 / box 2 are
   set), Ref2VA (6 fields, `<Subject N>` bound to the identity boxes in box order, `(S1)…` per subject). Lines →
   `(Sn) Name says <d>[Language] words</d>.` with one speaker registry per storyboard so `(S1)` is stable across
   cells. Golden tests, byte-for-byte, as the adapters have.
3. **The validator** (same file or `h3check.py`): the §1.1 structure, `<d>` canonical and equal to `lines`,
   speaker ids known, no `<Audio N>` when a soundtrack is kept, no second `Speaker N:` dialect in a video prompt.
   One-line refusals in the Hub's voice; refused before the job is queued.
4. **Frames from the lines**: syllable estimate (port HocusPocus's constants: 0.22 s/syllable and the pauses; a
   setting, not a constant) → `ceil(seconds × fps)` → `snap_frames` on the model's lattice → refuse over the
   one-pass maximum with "Split the lines across two clips". When a sound is set (V3), the sound decides instead
   (V3 note). The Seconds setting is the floor for a clip with no lines.
5. **Engine-published rules, not hardcoded**: the field names and letters per family, lattice, window min/max,
   fps and `deepy_prompt_infos` come from the capture (§1.3), through the upstream adapter's `native()`/`READS`;
   the compiler takes them as data. The Hub's system-prompt paragraph shrinks to routing: "a clip → fill `shot`",
   and the craft lines of §2 (stable speakers, budget speech, ending state carries) as guidance only.
6. **No polish pass** in the first stage (Gate 5 is optional in Director too).
7. **Speech and music** follow the same pattern, different dialect: speech already compiles in the engine
   (`Speaker N:`, Stage 12); a music model has its own `deepy_prompt_infos`; a `shot`-like object per kind
   (`lines` for speech, `song` {style, lyrics[], structure} for music) compiles to that kind's dialect. V2's tool
   decision (the assistant picks speech/music models) folds in here.

### 4.3 Invariants, read for this

- **5 (Generate renders the assistant's draft, never the prompt box):** holds. The `shot` object is the
  assistant's draft; the compiler renders it. The Hub adds structural labels and the engine's own alignment
  sentence, never prose of its own; HocusPocus's fixed sentences ("Same faces and wardrobe throughout",
  `HP:…/minimax_h3_prompting.py:195`) are **not** copied: that would be the Hub writing the film.
- **6 (the Hub adds no instructions; descriptions are labels):** holds; the compiler is rendering, exactly what the
  engine itself does for `Speaker N:` (`UP:…/dialogue.py:176-196`). The system-prompt paragraph stays in Open WebUI.
- **7 (settings, not constants):** words/syllable rates, the one-pass cap and the lattice are settings or engine
  facts.
- **Module imports only `hub.core.api`; files ≤300 lines:** compiler, validator and length live in
  `generate_image` as three files; the storyboard calls them through the Generate job kind as today.

### 4.4 What the screen shows

"Clip: Character 1 walks into the bar and says hello to Character 2." → the assistant fills `shot` (two subjects, one line,
camera, ending) → the Hub refuses in one line if the words or speakers are off, else compiles, sets the length
from the line, and renders. The visible draft on the Generate screen is the compiled Context-IR, editable; an edit
is re-validated, not rewritten (HocusPocus's idempotence rule).

### 4.5 Order

After Stage 12 (speech) and before V3 and the storyboard stage, since both of those write clip prompts and should
write `shot` objects from day one. One builder, one spec, three new files, goldens, tests of every refusal.

---

## 5. Rule checklist (each testable; E = the engine publishes it, C = client rule from upstream's own guidance)

| # | Rule | Source | Kind |
|---|---|---|---|
| 1 | Field names and order per family (3 for FL2VA, 6 for Ref2VA), each exactly once, no blank lines inside | `UP:…/prompt_enhancer.py:23-32, 108-121`; `HP:…/h3_prompt_policy.py:11-23, 41-55` | E (`deepy_prompt_infos`) |
| 2 | `[Shot 1]` first, no timestamp; later cuts `[Shot N] At MM:SS.mmm` increasing | `UP:…:32, 118` | E |
| 3 | Exact speech only inside `<d>[Language] words</d>`; nothing else inside | `UP:…:61, 256`; `HP:…/h3_dialogue.py:465-502` | E |
| 4 | Stable speaker ids `(S1)…`, first-vocal-event order, never moved to another mouth | `UP:…:61`; `HP:…/h3_prompt_policy.py:88-89`; registry `HP:…/h3_dialogue.py:1107-1150` | C |
| 5 | `<scenetrans>` at both sides of a line crossing a cut; `<cutoff>` only for a line the end interrupts | `UP:…:32, 256` | E |
| 6 | Visible lettering quoted separately, never as speech | `UP:…:32`; `HP:…/minimax_h3_duration.py:102-117` | E |
| 7 | Ambience/effects in `overall_soundscape`; audience score in `non_diegetic_music`; `N/A` when none; no voices in either | `UP:…:32`; `HP:…/h3_dialogue.py:1881-1900` | E |
| 8 | Soundtrack kept (`A`/`K`, `AS`/`KS`): "speaking with natural lip movements synchronized", speaker named, no transcript, no `<Audio N>` for the track | `UP:…:34, 116` | E |
| 9 | Labels `<Subject N>`, `<Picture N>`, `<Video N>`, `<Audio N>` numbered independently; start/end images first among Pictures | `UP:…:116` | E |
| 10 | Frame anchors declared with the fixed alignment sentence (start at 0.00; end at the exact end; both) | `UP:…:30`; `HP:…/h3_dialogue.py:1567-1593` | E |
| 11 | Speech budget ≈ 2 words/s (budget check) and length from syllables (0.22 s) + pauses, rounded up on 17n+5, within min/max, else split | `HP:…/h3_dialogue.py:652-690`; `HP:…/minimax_h3_duration.py:37, 120-156, 382-457` | C (rates), E (lattice, min/max) |
| 12 | One prompt unit per clip (`FG`); windows only with `PW`, blank line between, each window restarts at Shot 1 and time zero, Picture numbers remapped per window | `UP:wgp.py:1073-1086`; `UP:…/prompt_parser.py:46-60`; `UP:…/prompt_enhancer.py:36, 120` | E |
| 13 | Window commands `[/duration=…]`, `[/overlap=17k+1]`, `[/new_shot]` only at a window's start | `UP:…/prompt_enhancer.py:4-22`; `UP:…/frame_scheduler.py:102-118` | E |
| 14 | Dialogue needs `audio_plan.mode=dialogue_driven`, `timing_anchor=audio`, `lip_sync_critical=true`; silence must not claim an audio anchor | `HP:…/h3_dialogue.py:1838-1880` | C |
| 15 | Continue: next shot's opening state = previous ending state; no reset language | `MA:…/writing_contract.py:14-20`; `HP:…/validators/prompt_validator.py:166-177` | C |
| 16 | Don't describe silence or "no one speaks" as prose; H3 reads it as audio | `HP:…/h3_dialogue.py:1296-1299`; `HP:…/minimax_h3_duration.py:333-335` | C |
| 17 | The LLM's structured output is grammar-constrained; a polish pass must keep every `<d>` verbatim or is dropped | `HP:…/planners/base.py:72-237`; `HP:…/h3_story_contracts.py:106-140` | C |
| 18 | `Speaker N:` scripts only for the audio-only model; directions in `[ ]`; one turn per block | `UP:…/dialogue.py:30-45`; `UP:…/prompt_enhancer.py:123-129, 349-384` | E |

---

## 6. Worked examples (verbatim from source)

**Single shot, FL2VA, with speech** (`UP:models/minimax_h3/prompt_enhancer.py:82-84`):
```
integrated_multimodal_description: [Shot 1] At blue hour, a tired bicycle courier in a yellow raincoat pedals through a narrow rain-soaked market street. The camera tracks beside [the courier] at wheel height, then rises smoothly into a medium close-up as [the courier] stops beneath a flickering awning. Water runs from [the courier's] helmet while [the courier] catches [the courier's] breath, looks toward the closed train station, and says (S1) <d>[English] I missed it again.</d> Neon reflections ripple across the pavement and the shot holds on [the courier's] rueful smile.
overall_soundscape: …
non_diegetic_music: N/A
```

**Short form of the same** (`:26`): `integrated_multimodal_description: [Shot 1] The courier stops, turns to
camera and says (S1) <d>[English] Made it.</d>`

**Ref2VA with an identity and a voice reference** (`:236`): `The target video is an intimate, warmly lit workshop
portrait. [Shot 1] <Subject 1> sits at a crowded wooden bench under a brass task lamp … and says in the warm,
gravelly voice referenced from <Audio 1>, (S1) <d>[English] Patience is the smallest tool, and the hardest one to
hold.</d> [The subject's] lips, breath, and restrained smile stay synchronized with the line. …`

**First-frame anchor sentence** (`:30`; `HP:…/minimax_h3_prompting.py:20-23`): `For the target video, at 0.00
seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`

**Two-speaker script, audio-only model** (`UP:…/prompt_enhancer.py:123-128`):
```
Speaker 1:
[English, calm] …
Speaker 2:
[English, surprised] …
```

**Scene change inside one clip:** `[Shot 2] At 00:05.000, …` (`:32`). **Hard cut between windows:** a new
paragraph starting `[/duration=5s,/new_shot]` (`:14-19`). **Continue:** the i2va header plus the previous shot's
ending state as the opening (`HP:…/h3_dialogue.py:1575-1578`; `MA:…/writing_contract.py:16-18`).

**What Director compiles from a plan** (shape, `HP:…/minimax_h3_prompting.py:177-196`): `Visible subjects: (S1)
Character 1 …; (S2) Character 2 … Environment: … Chronological action: … (S1) Character 1 says <d>[English] …</d>. The shot holds a
medium shot with one coherent slow push in camera move. The shot ends on … .`

---

## 7. NOT FOUND and open

- No MCP server or tool schemas in either Director implementation (both are in-process; §2).
- No Context-IR validation in the engine itself (§1.2): the client must do it.
- The words-per-second and seconds-per-syllable rates are HocusPocus's choice, not engine-published; the Hub
  treats them as settings and measures on the server's GPU.
- Whether Open WebUI passes a nested object schema through to llama.cpp's tool-call grammar unchanged on the
  server's build (R19 says Native mode, Tool Search off); to be checked on the server with one tool call before the
  spec is final.
- Lip-sync quality and the mouth during computed silence: unmeasured (R20 §Unverified).
