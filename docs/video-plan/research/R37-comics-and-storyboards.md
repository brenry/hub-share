# R37 — Comics and storyboards from the Hub's pictures: engine, layout tools, current practice, 2026-10-17

Research note. Engine: upstream WanGP `af2ed29` (2026-10-12), read in a clone at `/tmp/upstream`. Hub read at the
working tree of 2026-10-17. Tool repos read in shallow clones under `/tmp/r37/`: comic-web-markup `4332e1b`
(2026-01-13), ComfyUI-IllustriousComicLettering `4a3e7a0` (2026-09-02), ComfyUI_Comfyroll_CustomNodes `d78b780`
(2024-01-24), agent-comic-kit `5e0e8d6` (2026-10-05), mangaharness/Kumanga `a87bc2b` (2026-10-02), inkstone `1113fba`
(2026-10-18 commit stamp), LianHuanAI `48de9f9` (2026-08-26). krita.org, img.ly, dev.to, budgetpixel.com and reddit
could not be fetched from this container (DNS or proxy refusal); items from them are marked *search summary*. The
GitHub API was closed, so licenses come from the cloned LICENSE files. Facts only. R8 §1 already covers
HocusPocus's Comic editor (one panel per page in storyboard mode); R16 §2 the picture task the Hub sends.

## 1. What the engine makes for multi-panel pages (af2ed29)

### 1.1 Image families in `defaults/*.json` and what they take
Each line: family (defaults files) — references — text capability noted in the defaults or model def.
- Flux 1 Dev / Krea / SRPO / Schnell (`flux*.json`), Flux 1 Chroma HD / Radiance (`flux_chroma*.json`) — none — none.
- Flux 1 Kontext, DreamOmni2 (`flux_dev_kontext*.json`) — `KI` or `I` (`models/flux/flux_handler.py:187-195`) — none.
- Flux 1 USO (`flux_dev_uso.json`, `flux_srpo_uso.json`) — subject + up to two style images
  (`flux_handler.py:179-185`) — none.
- Flux 1 UMO (`flux_dev_umo.json`) — several refs, "resized internally at 512x512 max" (`flux_dev_umo.json:5`) — none.
- Flux 2 Dev, Klein 4B/9B, pi-Flux2 (`flux2_*.json`, `pi_flux2*.json`) — `KI` or `I` (`flux_handler.py:187-195`) —
  none.
- Qwen Image 20B, 2512 — none — "capable to generate in the image very long texts" (`qwen_image_20B.json:5`);
  "long text rendering" (`qwen_image_2512_20B.json:5`).
- Qwen Image Edit / Edit Plus 2509 / 2511 (`qwen_image_edit*.json`) — `KI` or `I` (`models/qwen/qwen_handler.py:78-85`)
  — "very high quality images with long texts in it" (`qwen_image_edit_plus_20B.json:5`).
- Qwen Image Layered 20B — one input split into RGBA layers — none.
- Qwen Image 2.1 7B / Turbo (`qwen_image_21*.json`) — up to 10 ordered refs (`models/qwen21/qwen21_handler.py:136`)
  — "Text-rendering quality is moderate … Dense infographics are not a recommended use" (`:136`).
- Z-Image Turbo / Base / ControlNet (`z_image*.json`) — none (ref choices commented out,
  `models/z_image/z_image_handler.py:56`) — none.
- HiDream O1 Full / Dev / Dev 2604 (`hidream_o1*.json`) — `KI` or `I` (`models/hidream/hidream_handler.py:50-58`) —
  none.
- Krea 2 RAW / Turbo and Identity Edit (`krea2_*.json`) — Edit at most 2 (`models/krea2/krea2_handler.py:238-240`) —
  prompt help says "quote exact lettering" (`:93`).
- Ideogram v4 FP8 / NF4 / TurboTime (`ideogram4*.json`) — none found — "focused on typography, layout control,
  graphic design" (`ideogram4.json:5`).
- Ming Image 0.1 Design / Design-Layer — Design edits one ref (description); Layer takes exactly one
  (`models/ming_image/ming_handler.py:129-135`) — "Generate text-rich visual designs" (`ming_image_0_1_design.json:5`).
- SenseNova U1.5 8B MoT — one or more ordered refs (`models/sensenova_u1/sensenova_u1_handler.py:18-27`) — "Renders
  clearer Chinese and English text while following complex counts, layouts" (`sensenova_u1_5_8b_mot.json:5`).
- Wan 2.1 Chrono Edit (`chrono_edit*.json`) — one image to edit; makes a video internally, keeps the end frame — none.
- No Wan text-to-image default exists at af2ed29; Wan's `image_outputs` is set only for `chrono_edit`
  (`models/wan/wan_handler.py:921-925`). Kandinsky 5/6 defaults present are video.
- `KI` = first image is the main subject or landscape, then people/objects; `I` = all refs are people/objects. The
  general check refuses `I` with no picture (`wgp.py:1414-1416`); a model with `one_image_ref_only` refuses a second
  (`wgp.py:1420-1421`). No numeric ref cap was found for Flux 2, Qwen Edit, HiDream or SenseNova by grep.

### 1.2 Batch, modes, output
- `batch_size` is "Number of Images to Generate", a slider 1..`image_batch_size_max`, default 16
  (`wgp.py:12659-12662`); checked at `wgp.py:1059-1061` and `:7155-7157`. Every image default sets `batch_size: 1`
  (e.g. `defaults/qwen_image_20B.json:20`, `z_image.json:13`). Video models force `batch_size = 1` (`wgp.py:7164`).
- A batch is saved as separate files, one `save_image` per image (`wgp.py:8705`); the `make_grid` inside `save_image`
  (`shared/utils/audio_video.py:900-903`) receives one image at a time there.
- `image_mode`: 0 video, 1 image, 2 image inpainting (`wgp.py:1057`, `:1198`; inpaint modes `"image_modes": [2]`,
  `qwen_handler.py:69`).
- No grid, collage, page or comic output mode exists in any handler (grep for collage/comic/storyboard/manga/
  speech bubble over `.py`, `.json`, `.md`). Two related items:
  - Deepy's "Draw SVG" tool renders SVG markup (shapes, text, embedded gallery images) to a picture up to
    4096×4096, its description naming "character sheets, posters, storyboards, diagrams, layout guides"
    (`shared/deepy/engine.py:4333-4342`). It is an assistant tool, not a generation setting.
  - The MCP `view_media` tool can tile images "into a contact sheet" for inspection (`shared/mcp/v2.py:52`).
- Multi-panel pictures are made through the prompt only. Two defaults do so: Ming Design's default prompt is a JSON
  canvas with "four equal edge-to-edge vertical panels" (`defaults/ming_image_0_1_design.json:12`); Ideogram v4's
  default prompt is JSON with `aspect_ratio` and per-element `bbox` boxes (`defaults/ideogram4.json:14`), and the
  description says the Magic Prompt Enhancer "is a must use" (`:5`).

### 1.3 Size and aspect
- Preset list `shared/resolutions.py:40-80`: up to 1920×1088; portrait page shapes present are 1024×1536 (2:3),
  832×1104 (3:4), 624×832 (3:4), 1088×1920 (9:16), 1024×1792 (4:7); strips 1600×400 (4:1), 2048×768 (8:3).
- 4K presets (`shared/resolutions.py:14-36`, up to 4096×4096 and 5440×3072) appear only with the config
  `enable_4k_resolutions` = 1 (`wgp.py:2701`, `:11614`).
- Per-family caps (`resolutions_categories`): Qwen 2.1 and SenseNova `<=4096sq` (`qwen21_handler.py:84`,
  `sensenova_u1_handler.py:125`); Krea 2 and Ming Design `<=2048sq` (`krea2_handler.py:73`,
  `ming_handler.py:213`); Ideogram v4 `<=1440p` (`ideogram4_handler.py:191`); Ming Design-Layer `<=720p`
  (`ming_handler.py:123`).

### 1.4 What the Hub sends today
- Count 1..6 (`hub/modules/generate_image/screen.py:25`, `:36`); each picture is its own engine task with its own
  seed (`hub/modules/generate_image/build.py:285`, `:292-295`), each `batch_size: 1`, `image_mode: 1`
  (`hub/worker/adapters/tasks.py:97-98`).
- Width and height 256..4096, floored to the model's block (`build.py:272-273`).
- Reference cap per model from settings `ref_caps`, 1..6 (`hub/settings.py:43`, `:212-215`); refused above it
  (`build.py:71-72`). Default caps: `qwen_image_21` 6, `krea2_` 2.
- No page, panel, balloon or layout code exists under `hub/` (R8 §3 proposed a storyboard module; not built).

## 2. Free tools that lay out panels and balloons locally
- Krita 5.3 / 6.0 (desktop, GPL). 5.3.3 and 6.0.3 released 2026-07-29; 5.3 and 6.0 released 2026-02
  *(search summary)*. 5.3 adds a Comics Panel Editing Tool (vector panels) and on-canvas text editing; Krita ships a
  comic book manager, templates and a vector speech-balloon library *(search summary)*.
- Inkscape (desktop, GPL). 1.4.4, 2026-05-06 *(search summary, secondary catalog)*. Vector editor: frames, balloon
  shapes, text, SVG/PDF/PNG export.
- Scribus (desktop, GPL). 1.6.6 stable and 1.7.3 development, both 2026-04-13 *(search summary, Wikipedia)*. Page
  layout with image and text frames, PDF export.
- comic-web-markup (browser JS, MIT, `4332e1b` 2026-01-13). Text markup rendered to SVG panels; the engine places
  characters and balloons; CSS styles frames and balloons; live browser editor (README).
- ComfyUI-IllustriousComicLettering (MIT, 1.1.0 2026-09-02). Fixed 2×2 page, one bubble per panel, font text drawn
  with Pillow after VAE decode; wrap and font-size fit; tail length/width; bubble opposite the speaker, tail back;
  outputs image and bubble mask (README, CHANGELOG).
- Comfyroll "CR Comic Panel Templates" (no LICENSE file in the clone, `d78b780` 2024-01-24). Page 8..4096 px, grid
  templates or a custom row/column string, reading direction; one composite image
  (`nodes/nodes_graphics_template.py:265-372`); no balloons.
- ComfyUI "Comic Page Composer" (license and date not known) *(search summary, comfyai.run)*. Places generated panel
  images on a page from a JSON comic script; debug overlay; no balloons noted.
- Krita, Inkscape, Scribus run offline. comic-web-markup is static JS. The two ComfyUI packs need a ComfyUI install.
- Browser balloon makers found (BlankComic, Bubble Maker, LlamaGen tools) state no open-source license *(search
  summary)*.

## 3. What people use now for AI comic pages (dated)
- **Whole page, then split and fix** — agent-comic-kit (Apache-2.0, 2026-10-05): one page prompt with exact ratio,
  reference sheet roles, fixed appearance text, layout, one block per panel and "no text"; split on white gutters; a
  bad panel is redrawn alone at its slot ratio with the page as style reference; recompose on an exact canvas; face
  positions recorded so bubbles avoid faces with tails at the speaker; fonts Noto CJK. Backend GPT Image (hosted).
- **Whole page with blank lettering space, fonts overlaid** — inkstone (MIT, commit 2026-10-18): "finished-page mode"
  generates the page "with empty lettering chrome" and overlays caption, dialogue and SFX in real fonts "to avoid
  model-painted glyph distortion"; per-panel compose kept as a legacy mode. Consistency: prompt description plus
  reference img2img from a character portrait. Model: hosted Agnes API.
- **Panel editor with an asset library** — Kumanga/mangaharness (MIT, 2026-10-02): characters as poses × expressions
  collections; panels are clipping viewports; reference-image-aware generation via Gemini or any OpenAI-compatible
  endpoint (BYOK).
- **Deterministic lettering after generation** — IllustriousComicLettering 1.0.0 (2026-08-27) and 1.1.0 (2026-09-02):
  README rule "the image model … should not generate final dialogue".
- GitHub topic `comic-generator`, sorted by update, lists 13 repos updated 2026-08-18..2026-10-17; models named are
  hosted (FLUX via Replicate, GPT Image, Gemini, DeepSeek, Wan 2.7 Image Pro, CogView-4/GLM-Image) except one local
  SD 1.5 (CallmeTruong/Comic_Studio, 2026-09-14). LianHuanAI (2026-08-26) uses Tongyi `wan2.7-image-pro`, Zhipu
  CogView-4 / GLM-Image ("text_heavy_model"), RunningHub, Replicate FLUX/SDXL.
- Older than the window, for context: a note.com post (July 2026) names Qwen-Image-Edit for consistency from one
  reference with fixed model/LoRA/seed, and ComfyUI panel-layout nodes *(search summary)*; aurelm.com (2026-07-03)
  reports a ComfyUI page-by-page comic pipeline with Krea 2, FLUX Dev and Z-Image without refs or LoRAs
  *(search summary)*. Ideogram 4 open weights were released 2026-06-03, weights non-commercial *(search summary)*.
- img.ly's "Three-Panel Comic" benchmark asks for a fixed bubble line ("I forgot my keys") across ~14 models; Qwen-Image
  rendered the text right but in the wrong panel *(search summary; page undated, not fetched)*.

## 4. Not known
- Whether any engine model at af2ed29 lays out a readable multi-panel page with correct balloon text; no test here.
- Ref caps for Flux 2, Qwen Edit Plus, HiDream O1 and SenseNova inside their pipelines (no limit found by grep).
- Krita's comic manager state in 5.3.x/6.0.x and its exact feature list (krita.org not reachable).
- License and last commit of the "Comic Page Composer" node; Comfyroll's license.
- Any Reddit thread on AI comic pages in the last 60 days (reddit not reachable; searches returned none).
- Whether Ideogram v4's `bbox` JSON places panel borders and text where boxed, on this engine.

Sources (web): [Krita releases](https://krita.org/en/categories/officialrelease/),
[Krita 5.3 notes](https://krita.org/cs/release-notes/krita-5-3-release-notes),
[Scribus (Wikipedia)](https://en.wikipedia.org/wiki/Scribus),
[comic-web-markup](https://github.com/abuseofnotation/comic-web-markup),
[IllustriousComicLettering](https://github.com/katorikonoe-ai/ComfyUI-IllustriousComicLettering),
[Comfyroll](https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes),
[Comic Page Composer](https://comfyai.run/documentation/ComicPageComposer),
[agent-comic-kit](https://github.com/Saeyeon-developer/agent-comic-kit),
[inkstone](https://github.com/phaethix/inkstone),
[Kumanga](https://github.com/BotTony329/mangaharness), [LianHuanAI](https://github.com/williamjxj/LianHuanAI),
[GitHub topic comic-generator](https://github.com/topics/comic-generator?o=desc&s=updated),
[note.com manga in ComfyUI](https://note.com/asayi_megumi/n/n97f2527d8502?hl=en),
[aurelm.com comic generator](https://aurelm.com/2026/07/03/from-infinite-scene-images-to-infinite-comic-books-comfyui-first-comic-book-generator-from-a-simple-story-with-consistancy-using-no-references-loras-etc/),
[img.ly comic-strip benchmark](https://img.ly/ai-benchmarks/prompts/g05-comic-strip/),
[Ideogram 4 review](https://invideo.io/blog/ideogram-ai-image-generator/).
