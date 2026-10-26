# The Open WebUI system prompt for the Hub

Status: the block below is the whole Open WebUI system prompt of the model the Hub talks to; it speaks to the model as "you" and names what was typed in the chat as "the chat message". The Directing rules are the Hub's planner's (`hub/modules/director/sayask.py`), not the block's. Adapted from `research/R5-assistant-contract-risks.md` §2.8 and the
contract of `docs/architecture/parts/04-assistant-mcp.md` §4.5.2: the assistant has the six Generate tools
(`get_generate_image_settings`, `set_generate_image_settings`, `list_image_models`, `list_loras`, `list_characters`,
`generate_image`), `direct_clip`, `direct_scene`, `redo_shot`, plus the four of the sequence module
(`list_sequences`, `list_sequence_clips`, `add_last_clip`, `join_sequence`; Stage 11), and the eighteen script tools
(`script_say`, `script_start`, `context_set`, `scene_add`, `scene_change`, `shot_add`, `line_add`, `cue_add`, `pose_add`,
`event_move`, `event_change`, `event_remove`, `script_read`, `script_lock`, `script_unlock`, `script_track`,
`script_stems`, `script_render`), thirty-one in all. The model is picked in Generate's pulldown and the pictures placed in
the boxes; the tools report both (`model`, `model_name`, `references`) and set neither (the screen's pick only, ever). The block teaches the draft, pictures and spoken lines, and hands a clip's or a
scene's request and a shot's redo to the Hub, and every message of a script chat to `script_say`; the four sequence tools carry their own descriptions.

Paste the block below as the whole Open WebUI system prompt of the model the Hub talks to, in place of everything
there now. It stands alone: no other rules are needed before or after it. It holds no names, paths or keys, and
names no model. About 690 words. Clips land flat by day, newest first.

```text
THE HUB. You write prompts for the Generate screen in the Hub, through its tools. Every draft goes to the Hub, never
into this chat: write it with set_generate_image_settings {draft: "<the whole draft>"}, and revise it the same way.
It appears in the draft panel beside the chat. Your chat reply is one short line, never the draft. generate_image
renders the draft that is in the Hub and nothing from this chat; if it says the draft is empty, set the draft first.

THE MODEL IS THE SCREEN'S. The model is picked in the Generate pulldown. Never send model or references; for a shot,
the Hub puts the characters you name into empty boxes itself. Before writing a draft, call get_generate_image_settings
and write the draft for the model it shows (model_name) and the boxes it shows (references, in box order). If the chat
message needs another model or other pictures, say so in one line, write no draft and do not render.

When to render. The first chat message about a new idea (a picture or a spoken line) sets the draft only and does not
render. A later chat message about it revises the draft with set_generate_image_settings, then calls generate_image. A
chat message that only changes a setting sets that one setting, leaves the draft alone and does not render: "540p" ->
megapixels 1; "720p" -> megapixels 2; "16:9", "9:16" or "1:1" -> aspect; "20 steps" -> steps 20; "3 pictures" ->
count 3. If the Hub refuses something, reply with its line, word for word.

Pictures. On a picture model the draft is the picture's prompt: English, plain text, under 4000 characters.
list_characters gives each character's name and its notes; use the notes as background for a character in the
boxes, never as words to copy. To keep a picture the chat message names, set seed to one of last_seeds from
get_generate_image_settings. A LoRA the chat message names: call list_loras {model: "<model from
get_generate_image_settings>"} and set loras with its id and a strength. After generate_image say the picture is
queued and will appear in Media.

Clips. Any request for a clip, a video, an animation or anything that moves: call direct_clip {request: "<the chat
message's words, exactly as written, without Clip:>"} and nothing else: no shot, no draft, no generate_image. Reply in
one line with what it answers. The Hub plans the clip, checks it and renders it itself.

Scenes. A request that starts with Scene:, or asks for a scene, several shots or more than about 15 seconds: call
direct_scene {request: "<the chat message's words, exactly as written, without Scene:>"} and nothing else, not
direct_clip. Reply in one line with what it answers. The Hub plans the shots, renders them and cuts them together
itself.

Redo. A request to redo, re-render or try again one shot of a scene (Redo shot 3, or Redo shot 3 of <title>):
call redo_shot {shot: 3} (with scene: "<title>" only when the chat message names one) and nothing else. Reply in one
line with what it answers.

Scripts. Every chat message in a chat about a script goes to script_say {words: "<the chat message, exactly as
written>"}, once and nothing else, even when it asks for a video or a render; reply with its line as written and say
nothing it does not say. A first chat message that tells a story starts the script.

Spoken lines. When the chat message asks a character to say something, the draft for the speech model is the spoken
words only, as the chat message gives them. One optional [ ] first for language, emotion or pace, for example
[English, calm] The light is ours tonight. No Speaker header, no six fields, no <d> tags, no other [ ]. About 2.6
words per second. If the Hub refuses the line, rewrite it to this shape and send it again. A line's result (last_take
in the settings) says how many of its words were heard; under the bar the Hub makes another take by itself; if the bar
is still not met, shorten the line or split it in two.
```

## What each line rests on

- **Scripts.** The paragraph is one rule; render, done, a costume, how a picture is used and every change are read by the Hub from the chat message's words (`say.py`, `sayplain.py`, `sayask.py`), and the Directing a script paragraph below is no longer in the block: the Hub's planner holds its rules (`sayask.STORY`). Every script message is one `script_say {words}` call
  (`hub/modules/director/say.py`): the Hub asks its own model for the operations (`sayask.py`), checks the chat message's words
  against them (`saycheck.py`) and answers its own line; in the Hub's chat any writing script tool reads the chat message
  from the chat. Called directly, `script_start {name, story}` (`hub/modules/director/tools.py`,
  `script_start`) asks the configured model for the context (`hub/modules/director/start.py`) and answers with the next step,
  "now write the story: scene_add, shot_add, line_add"; the story is then written one event per call,
  each checked on arrival and refused as `{problem, fix, hints}` (R48 §2). The block's "In this chat call only the
  script tools" sentence is also said by `script_start`'s answer and by the descriptions of `generate_image`,
  `direct_clip` and `direct_scene` ("Not for a chat started with Script:, which the script tools write."),
  so it reaches the model from the Hub as well. The paragraph Directing a script teaches directing from R49 (`docs/video-plan/research/R49-dialogue-coverage-and-exchange.md`), each sentence on
  its numbers: S1 several shots: 1.1, 1.14, 3.2, 7.2.3. S2 open wide or on a two-shot; singles and OTS; the reaction
  shot holds the other's line: 1.4, 1.5, 7.1.2, 7.1.6; 1.6, 1.7, 1.14, 7.1.5; 1.11, 7.1.8. S3 where to cut, not the
  "Dragnet" cut: 7.2.7, 2.2; 7.2.1, 7.1.6; 7.2.8, 7.6 on 2.7, 7.1.8. S4 the camera, framing, who and the reason:
  7.1.1, 7.1.3, 1.4, 1.7, 1.13; 7.4.2; 2.3, 7.2.5, 7.2.6. S5 an important line, no close-up owed: 7.1.8, 7.2.4, 7.6
  on 1.5. S6 the exchange, the beat, the turn: 7.5.1, 7.5.3, 7.5.2, 5.1, 5.2, 5.8, 5.6, 7.3.5. S7 own words, short,
  not the narration, not what both know: 5.4, 7.5.6, 7.5.5, 5.5, 7.3.5. S8 questions and answers: 5.9, 7.3.5. S9 a cue only
  where called for: the story's sound is the limit; the audience 7.3.6, 4.4. S10, the length, is the length check below
  (`hub/modules/director/length.py`); it teaches no craft. The descriptions of `scene_add`, `scene_change`,
  `shot_add`, `line_add` and `cue_add` say what their fields hold (`hub/modules/director/teach.py`,
  `SAY` and the R49 numbers in `CITES`). A length the chat message names is the scene's `seconds` (`scene_add`, `scene_change`),
  kept within 10 %: a write that carries a scene past 110 % and makes it longer is refused with the seconds and words
  over, a new scene is refused while an earlier one is outside 90-110 %, and every shot line of the answers shows the
  scene's length against its range (`hub/modules/director/length.py`); the last scene is never refused for running
  short. R49 gives no rule for segment order (the escalation is not Grindstaff's), for cutting to the replier as the replier
  begins (Murch corrects it), for seconds or lines per shot, for how long a look, an establishing shot or a reaction
  is held, for a camera plan of a production with an audience, for a close-up on an important line, for where an effect or music cue goes,
  for the written interruption or split edits, or for the 180- and 30-degree rules (staging): not taught.
  The blueprint's §7 (only the hand-over lines) is excepted. The
  sentence on changing names what the chat message named as a `ref` (`{speaker, nth}`, `{cue, nth}`, `{shot: n}`), which the Hub
  resolves on the file (`hub/modules/director/refs.py`), every edit's answer starting with what it took the chat message to mean
  and every answer listing the scene's lines with their numbers. The
  Scripts paragraph says a message telling more of the story goes to the add tools and one asking to change, remove
  or move something to the change tools on what the chat message named; a silence the Director's call would leave inside a shot is
  refused at that call with where to close it (`hub/modules/director/air.py`); an empty shot can be taken out with
  `event_remove` and is refused at `scene_change {done}` and at the lock; `scene_change` answers how far the scene
  runs under or over the length the chat message asked, its dead air and a fix line.
- **A shot of a scene redone.** The model copies the shot's number and,
  only when the chat message names one, the scene's title: `redo_shot {shot, scene?}` (`hub/modules/generate_image/tools.py`,
  `redo_shot`), which answers at once with the queued job. The Hub renders that shot's kept plan again on the next
  seed and cuts the scene again with it (`hub/modules/generate_image/redo.py`); the new take replaces the old in the
  scene's Edit Video sequence, and the old take and the old cut stay in Clips. The plan is kept in memory only, so a
  scene made before the Hub last started (every install restarts it) cannot be redone; the Hub says so on the card.
- **Scenes go to the Hub whole.** As a clip: the model copies the chat message's
  words into one string, `direct_scene {request}` (`hub/modules/generate_image/tools.py`, `direct_scene`), which
  answers at once with the queued job; the Hub asks the model in Settings -> Assistant for the whole scene (title,
  cast, set, 2 to 8 shots) as one JSON object (`hub/modules/generate_image/scene.py`, `MESSAGE`, which says
  "Scene plan:", not "Scene:", so this paragraph's hand-over does not fire on it), checks every shot as one shot is
  checked, renders the shots in order and cuts them with Edit Video's join, as one job. The model routes by the prefix
  only (`Scene:` here, `Clip:` above) and by the length the chat message asks: one pass holds about 15 s, so "more than
  about 15 seconds" is a scene. "not direct_clip" is added to the paragraph's words: the Clips
  paragraph's "anything that moves" also covers a scene, and this names which call wins. Each shot lands in Clips as it is made, the cut last; Edit Video holds a sequence
  named by the scene's title.
- **Clips go to the Hub whole.** The model copies the chat message's words into
  one string, `direct_clip {request}` (`hub/modules/generate_image/tools.py`, `direct_clip`), the smallest thing a
  tool call carries; the tool answers at once with the queued job, so Open WebUI's turn is over before the Hub asks
  the model in Settings -> Assistant for the shot (`hub/modules/generate_image/director.py`). The Hub's own message
  (`director.MESSAGE`) carries what the removed paragraphs carried: one speaker per shot and no audience face while
  anyone speaks (E6), spoken words in `lines` only (E7), the audience's sound a placed bed (E4), and a word budget
  from the model's longest pass. It asks "Shot plan:", not "Clip:", so this block's hand-over does not fire on it
  if Open WebUI adds the configured model's system prompt. Every refusal is the Hub's line on the Generate card;
  three refusals fail the job in one line. The bullets under "The record" below on clip drafts, the Director, a continued clip and a
  clip's result are the record of the paragraphs taken out of the block; the rules live on in the Hub's message, in
  the compiler (`shotprompt`, `shotcheck`) and in the press.
- **The draft goes through the tool.** The draft panel shows the session's draft, which only
  `set_generate_image_settings {draft}` writes (`hub/modules/generate_image/screen.py`, `apply`); a draft written as a
  chat reply never reaches it, and `generate_image` then refuses "The draft is empty" (`tools.py`, `generate_image`).
  A block that says "write the draft" without naming the call leaves the model no call to write it with, and the
  draft lands in the chat. The block names the call and carries the
  picture rules itself (`docs/architecture/parts/04-assistant-mcp.md` §4.5.2), so it is the whole system prompt.
- **Pictures.** The rules are §4.5.2's contract, less references by name: the notes
  come only from `list_characters` (`cast.listing`); `last_seeds` is the seeds of the last render of this model
  (`screen.last_seeds`) and `seed` takes one as text; `list_loras` takes the model id (`hub/modules/loras/tools.py`)
  and `loras` is checked against that model's folder with a strength from 0 to 2 (`screen._loras`); `count` is 1 to
  6 (`screen.COUNT`). A picture lands in Media.
- **The model and the boxes are the screen's.** The tool server publishes no `model` and no `references` setting
  (`hub/modules/generate_image/screen.py`, `SETTINGS`); a call that sends either is refused by the schema check
  ("unknown argument model", `hub/core/schema.py`), never obeyed. `get_generate_image_settings` still reports `model`,
  `model_name` and `references`, so the assistant writes for the screen's pick. When that pick cannot run the tools say
  "The model picked on the Generate screen cannot run; pick one there" and no other model is chosen. The block has
  no words "image" and "video" and no "switched the model" notice.
- **Draft.** The draft is refused while no Generate window is open (`screen._draft`).
- **Count 1.** Any count other than 1 on a clip model is refused with "<model> makes one clip at a time"
  (`screen.py:248-253`). `get` reports count 1.
- **540p / 720p -> megapixels.** The megapixels value picks the tier: 1 or less the first offered tier (540p), 1.5 and
  2 the second (720p), 4 the third, or the last offered when there are fewer (`models.py:92-98`). The Hub offers 540p
  and 720p (`models.py:19`), so the choices of the `megapixels` setting that matter for a clip are 1 and 2
  (`screen.py:24`).
- **Aspect and steps.** `aspect` is one of auto, 1:1, 4:3, 3:4, 3:2, 2:3, 16:9, 9:16 (`screen.py:22,36`); a clip's
  `auto` is square (`screen.py:54-61`, `models.py:97`). `steps` is a whole number within the model's own range
  (`screen.py:198`): the pruned model takes 1 to 50, the 4-Step model 4 to 8 (R1 §1.1), so "20 steps" is for the
  pruned model.
- **Rendering.** `generate_image` is a press of Generate; it answers at once with the job state and a hold text if
  the job waits (`tools.py:50-80`). A clip and a picture share one engine lane, so a clip waits behind a picture and
  the other way round (plan §4). The finished clip lands on the Clips page, not in Media.
- **4000 characters.** `MAX_PROMPT` is 4000 for the screen (`screen.py:28`); a longer draft is refused with "draft is
  too long (at most 4000 characters)" (`screen.py:216-217`), and the job builder refuses a longer prompt too
  (`hub/modules/generate_image/build.py:94-95`). R1 §3.3 names a higher cap for a video module; the screen keeps
  4000.
- Spoken lines: the Hub puts `Speaker 1:` before the draft (`hub/worker/adapters/tasks.py`, `speech`);
  the engine cuts its prompt at every `Speaker N:` and fails a turn with no words outside `[ ]` (upstream
  `models/minimax_h3/dialogue.py:44-45, 124-131`), so the draft carries no header and has words outside `[ ]`. The
  Hub refuses such a draft in one line, and the paragraph tells the assistant to rewrite it. Pace: upstream
  `dialogue.py:23` (2.6 words per second).

## The record: lines no longer in the block

The paragraphs these rested on are not in the block; these lines are kept as their record.

- **One speaker per shot; no quoted words outside `lines`.** The Hub turns the speaker's voice from the speaker's sample
  after the render with the engine's SeedVC, one speaker: every voice in the clip is converted to the one sample
  (upstream `postprocessing/seedvc_processor/bridge.py:381`), so a shot with two speakers, one of them sampled, is
  refused ("One speaker per shot when [the speaker's] voice is converted"). No audience lips move while a character
  speaks. Any field but `lines` holding a quote mark, `<`, `>` or "says" is refused in one line naming
  the field (`shotcheck.no_speech`): the engine reads quoted text as lettering and speech only inside `<d>`
  (upstream `models/minimax_h3/prompt_enhancer.py:32`, `:61`); the Hub refuses rather than rewrites. A cutaway
  pictures the audience; its sound stays a placed bed (E4, E6). The block speaks to the model as "you" and to what was typed as "the chat
  message".
  The block names the three things `shotcheck._speech` refuses (`shotcheck.py:40-41`, `:124-133`).
- **Model ids.** `list_image_models` returns `{id, name, size, steps, loaded}` for every model that can run; the
  assistant reads it to say which model a request would need. The pruned model's name in the engine's definition is
  "H3 First / Last — Pruned" and the fused one's is "H3 Fused 4-Step — Frames (Experimental)". An engine that names
  them differently takes the two quoted labels ("First / Last" and "Omni") of the block changed to its names.
- **Seconds are not a tool setting.** `SETTINGS` has no frames or seconds (`screen.py:30-44`); the length is the model's
  `advancedByModel[model].frames`, edited in Settings → Generate Image as Seconds, snapped up to the frame grid
  (`screen.py:75-78,195-196`). `get_generate_image_settings` reports `frames` and `seconds` for a clip
  (`screen.py:176-178`). The assistant can only read them.
- **Three fields.** The engine's H3 prompt contract is `integrated_multimodal_description`, `overall_soundscape`,
  `non_diegetic_music`, in this order (R1 §3.1). The first field carries the scene and the camera and its motion; the
  second and third carry the sound. Nothing in the Hub rewrites the draft: the worker forces no enhancer
  (`hub/worker/wan2gp.py:43-44`).
- **No `#` or `!` at line start.** The engine's template parser drops a line starting with `#` and reads one starting
  with `!` as a macro (R1 §0.5).
- **Speech.** Only text inside `<d>[Language] …</d>` is spoken, the speaker id goes just before the tag, and the
  engine's own check allows about 2.1 words per second (R1 §3.1).
- **Sound.** The clip keeps the sound H3 makes (plan decision 5). Described sounds become audible, so a silent clip
  wants `overall_soundscape: N/A` (R5 §2.5). For clips silent by default, the sentence after "never speech." becomes
  "Write N/A."
- **Start frame and identities (Stage 4).** On the First / Last model, box 1 is sent as the clip's first frame
  (`image_prompt_type "S"`, R1 §1.4); a Character picked by Tab or dropped fills it like any picture. On the Omni model each box is one identity reference (`image_intent: identity`,
  R1 §1.5) and the engine needs at least one image; the Omni model cannot run text only (Stage 3). Aspect Auto snaps
  to the nearest tier aspect of the box 1 picture, so the assistant leaves aspect alone.
- **The alignment line.** The first line for a start frame is the engine's official form (R1 §1.4, §3.1). If the Hub
  is later changed to write that line itself, delete the sentence "With a start frame, put this line first: ..." from
  the block.
- **Omni fields.** The six fields and the retention values are R1 §3.2. MiniMax suggests 350 to 500 words for
  `detailed_description`; the block says about 250 because the screen's 4000-character cap (`MAX_PROMPT`) applies
  to the whole draft.
- **Text encoder.** It moved to the raised sheet next to Guidance; it is not one of the assistant's settings, so the
  block tells the assistant to say so. The memory profile stays in Settings, Engine.
- **Last frame (Stage 5).** On First / Last, box 1 is the start frame and box 2 the last frame
  (`image_prompt_type "SE"`, `image_start`, `image_end`; R6 §4.1). The boxes are filled on screen; a third picture is refused by
  the Hub in one line.
- **The alignment line stays in the block.** R6 §4.1 (Prompt) puts the `<Picture 1>` at 0.00 and `<Picture 2>` at the
  exact end time lines into this paragraph ("One sentence added to `system-prompt-video-paragraph.md`"), and nothing in
  R6 says the engine or the Hub writes them: the Hub's code has no such line (only a test string mentions
  `<Picture 1>`, `tests/engine/test_video_refs.py:195`), and the engine only advises the enhancer to write it
  (`prompt_enhancer.py:16-20`, `:120`; no enhancer is forced, `hub/worker/wan2gp.py:43-44`). So the sentence is kept
  and extended. The second clause is modelled on the first; the engine gives the first line's exact wording
  (`prompt_enhancer.py:120`) and only the meaning of the second (`:20`), so its wording is not the engine's. The end time is the
  `seconds` that `get_generate_image_settings` reports. If the Hub is later changed to write either line, delete it
  from the block.
- **Continued clip (Stage 6).** A clip placed in box 1 (Media's Continue, or a clip dropped on box
  1) goes to the picked model when that model continues a clip, else one line: "<model> cannot continue a
  clip" (`chain.continue_clip`). The assistant does not place one: `references` is no setting. With a clip in box 1
  the settings report the clip's `width` and `height` and `seconds` as the step, so aspect and megapixels have no
  effect and the block says to leave aspect alone. The draft has no `<Picture 1>` line because the clip is the video
  source, not a picture (R7 §5); the same `overall_soundscape` words, because sound does not carry across jobs (R7
  §2.1); speech only for the new seconds, because the earlier ones are already in the clip. The scene may be refused
  for length ("The scene would be <s> s; the longest is <cap> s"); the assistant relays the line.
- **Omni's detail and cut-out (Stage 7).** Detail is a menu on the raised sheet and the cut-out a toggle on each identity box's menu, set on screen, kept in the
  card and the boxes and not among the tool server's settings (`detail` is not in `SETTINGS` or `view()`;
  `cutout` is read from the session boxes by `generate_image`, `tools.py:74-75`). A picture outside 1:4 to 4:1 on Omni
  is refused when the job is built, with "Identity <n> is <w>×<h>: <label> takes pictures between 1:4 and 4:1"
  (`cast.shape`, called from `build.py`), so the assistant hears the line from generate_image and says it in the chat.
  The names that go with the pictures (`character_name`, `build.py`) need no sentence: the boxes as placed carry
  them. Name lines for the six fields (a name in `subject_definitions`, a speaker's name before a spoken
  line) are not in this block; add them if "<name> says ..." is wanted, trimming first.
- **Boxes as `<Picture N>`, in box order (Stage 9 step 5; R16 §4 rule 8).** On upstream WanGP nothing in the task
  binds a picture to a name: the identities go as `image_refs` in box order, and the engine numbers its pictures
  (start, end, injected frames, then references) and reads `<Picture N>` in the prompt to bind them
  (`minimax_h3_handler.py:109, :173, :179`). The fork's per-picture `character_name` has no upstream place, and the Hub
  adds no words to the prompt (invariant 6), so the binding is the assistant's: one `subject_definitions` line per box,
  in box order, `<Subject N> is <Picture N>`. On the fork the names still travel with the boxes as well; the line does
  no harm there.

## What this paragraph does not do

- It does not change the length of a clip, the text encoder, the memory profile, LoRAs or the muxer tags; those are
  not tools.
- It does not use Omni audio and video references, timed pictures, or a last frame alone; the Hub sends none (R6 ranks 4 to 9).
- It does not teach the sequence tools: joining clips into one file is `join_sequence`, queued by the sequence module
  and described by the tool itself. Nor does it set a scene's length cap (`continue_max_seconds` is a setting) or pick between
  branches of a scene; "Continue" always continues `last_clip`.
- The assistant cannot see the clip; it is told only that the job was queued.
