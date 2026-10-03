# Universal AI Video Editing & MCP Integration Guide for Kinetic Cut

This document serves as the master operational guide for any AI assistant, automated pipeline, or agentic workflow connecting to Kinetic Cut via the Model Context Protocol (MCP). It defines universal creative standards, technical tool contracts, framing mathematics, and algorithmic workflows required to produce broadcast-grade vertical videos (9:16 Shorts, TikTok, Reels) across **any genre, topic, or niche** (e.g., science explainers, gaming recaps, tech reviews, historical mysteries, financial breakdowns, fitness, podcasts, or narrative drama).

---

## 1. Universal Creative Principles (Applicable to Any Topic)

Regardless of the topic, high-retention short-form video adheres to strict human attention patterns:

1. **The 3-Second Hook Rule**:
   - The opening 0 to 3 seconds determine whether a viewer swipes or watches.
   - Combine a punchy opening thesis or question, a dynamic visual (focal point centered, with camera push-in or punch zoom), and an immediate sound cue.
2. **Pacing & Shot Duration Limits**:
   - Total runtime should target **40 to 58 seconds** for optimal completion rates.
   - **Maximum static shot duration is 3.5 to 4.5 seconds**. Every shot must feature continuous procedural motion (Slow Push-In, Ken Burns, Pan) or cut to a fresh visual angle before viewer fatigue sets in.
3. **Pillarbox Void Elimination (100% Canvas Coverage)**:
   - Vertical viewers disengage when seeing bare black voids at the top and bottom of horizontal 16:9 media.
   - Always implement **dual-track vertical compositing**: an ambient blurred/darkened background on `video_1` and the focused foreground subject on `video_2`.
4. **Focal Point & Subject Centering Awareness (9:16 Canvas)**:
   - Standard horizontal footage or photography places subjects anywhere in the 16:9 frame (left third, right third, top, or bottom).
   - Placing such media into a 9:16 vertical canvas (1080×1920) without positional offset will cut off the subject.
   - **Crucial Requirement**: Every AI editor must evaluate where the subject of interest is located (e.g., a presenter's face, a gameplay character, an athlete, a product close-up, or a key document detail) and configure `transform.x`, `transform.y`, and `transform.scale` so the subject sits prominently in the vertical safe zone (the upper-middle 60% of the canvas).
5. **Multi-Track Layered Audio Hierarchy**:
   - **Voiceover (`audio_1`)**: Primary clarity driver (`role="source_audio"`), mastered at `+1.0 dB` to `+1.5 dB`.
   - **Music Bed (`audio_2`)**: Sets emotional tone, mastered at `-14 dB` to `-18 dB`. Auto-ducking MUST be enabled (`duck_amount_db: -11.0 dB`) so music recedes whenever speech occurs.
   - **SFX Bed (`audio_3`)**: Accentuates scene transitions and emotional beats (e.g., transition swooshes on cuts, impact hits/risers on dramatic reveals).
6. **High-Contrast Synchronized Typography**:
   - Rapid word-by-word animated subtitle cards (`bounce`, `pop`, `karaoke`) synchronized to spoken syllables.
   - Positioned safely at `position_y: 0.72` to `0.78` to avoid TikTok/Reels UI overlay cutoffs.

---

## 2. Kinetic Cut MCP Tool Architecture

Kinetic Cut exposes a comprehensive set of automated tools via MCP (HTTP JSON-RPC on port `10101` when started with `--enable-mcp`).

| MCP Tool | Purpose | Key Parameters |
| :--- | :--- | :--- |
| `get_capabilities` | Introspect available features, filters, presets, and commands | None |
| `get_state` | Read project settings, playhead position, active tracks, and jobs | None |
| `get_timeline_summary` | Token-efficient structured JSON of all tracks, clips, audio gains, and caption word cards | None |
| `project_file` | Open, save, or query project files (`.kcut`) | `operation: "open" \| "save"`, `path` |
| `apply_edits` | Perform atomic timeline manipulations (insert, split, move, delete, adjust) | `operations: [...]` |
| `synthesize_dialogue` | Headlessly generate neural voiceover and auto-place on timeline | `text`, `voice`, `start`, `track`, `gain_db` |
| `apply_visual_fx` | Assign and configure any of the 37 procedural motion/camera/zoom effects | `item_id`, `effect`, `properties` |
| `apply_vertical_framing`| Automatically composite vertical foreground/background blur pairs | `mode`, `foreground_track`, `background_track`, `scale` |
| `set_caption_style` | Apply curated styling presets or bespoke typographic properties | `preset`, `properties` |
| `generate_captions` | Headlessly trigger Whisper transcription and create animated word cards | `headless: true`, `words_per_card` |
| `seek` | Reposition the playhead to an exact timestamp | `seconds` |
| `get_preview` | Capture the current rendered preview frame for visual inspection | None |
| `inspect_ui` | Scan live UI controls, modal dialogs, and button pointers | None |
| `ui_control` | Programmatically operate UI buttons, tabs, or dialogs | `operation`, `target`, `value` |

---

## 3. Universal Step-by-Step Editing Workflow

Follow this standardized sequence for **any** video prompt, topic, or narrative idea.

### Phase 1: Asset Discovery (Never Hardcode Project Media)
Before constructing timeline operations:
1. Call `get_state` or `get_timeline_summary` to inspect the media pool of the open project.
2. Note the available `media_id`s, durations, resolutions, and file paths.
3. If creating a brand new project, import required user assets first or generate voiceovers dynamically via `synthesize_dialogue`.

---

### Phase 2: Narrative Beat Structuring (Universal 5-Beat Arc)
Divide any topic into a 5-beat rhythm designed for ~45 seconds of content:
- **Beat 1: The Hook (0.0s – 5.0s)**: High-curiosity question or shocking premise.
- **Beat 2: The Context (5.0s – 15.0s)**: Introduce the environment, character, or problem.
- **Beat 3: The Turning Point (15.0s – 28.0s)**: Rising tension, unexpected event, or central obstacle.
- **Beat 4: The Climax / Peak (28.0s – 40.0s)**: The resolution, critical action, or dramatic breakthrough.
- **Beat 5: The Takeaway (40.0s – 50.0s)**: Philosophical reflection, lingering mystery, or call to comment.

---

### Phase 3: Voiceover Synthesis (`synthesize_dialogue`)
Synthesize speech for each beat. Place voiceovers sequentially on `audio_1` with `gain_db: 1.2`.

> [!NOTE]
> **Illustrative Example: Voiceover Synthesis Call**
> ```json
> {
>   "text": "Your compelling opening hook statement goes here.",
>   "voice": "adam-narrator",
>   "start": 0.0,
>   "track": "audio_1",
>   "gain_db": 1.2
> }
> ```
*Tip*: Capture the returned clip duration. Use each voiceover clip's duration to anchor the visual cuts and sound effects.

---

### Phase 4: Visual Media Placement & Intro Trimming (`apply_edits`)
Sequence B-roll clips and still images onto `video_2` to match the narrative beats.

> [!NOTE]
> **Illustrative Example: Visual Clip Insertion**
> ```json
> {
>   "operations": [
>     {
>       "op": "insert_clip",
>       "media_id": "<target_media_id_from_project>",
>       "track": "video_2",
>       "start": 0.0,
>       "duration": 4.5,
>       "in_point": 1.0,
>       "role": "normal"
>     }
>   ]
> }
> ```
*Quality Rule*: Always inspect source media for opening watermarks, channel intros, or title slates. Set `in_point: 1.0` or higher to trim past unwanted graphics directly into the action.

---

### Phase 5: Vertical Framing & Focal Point Centering

#### A. Background Ambient Blur Fill:
For every clip on `video_2`, insert a matching clip on `video_1` with `role="background"`:

> [!NOTE]
> **Illustrative Example: Background Blur Fill Pair**
> ```json
> {
>   "op": "insert_clip",
>   "media_id": "<target_media_id_from_project>",
>   "track": "video_1",
>   "start": 0.0,
>   "duration": 4.5,
>   "in_point": 1.0,
>   "role": "background"
> }
> ```
Alternatively, call `apply_vertical_framing` with `mode: "center_and_fill"`.

#### B. Focal Point & Subject Centering Formulas (`transform.x`, `transform.y`, `transform.scale`):
Never assume the subject is in the center of a 16:9 frame. When crop to 9:16 occurs:
- **Subject on Left Third**: Set `transform.x: 0.22` to `0.35` to shift the subject rightward into the vertical viewport.
- **Subject on Right Third**: Set `transform.x: -0.22` to `-0.35` to shift the subject leftward into center.
- **Subject Low in Frame**: Set `transform.y: 0.10` to `0.20` to elevate the subject above the lower caption boundary.
- **Subject High in Frame**: Set `transform.y: -0.10` to `-0.20` to keep the subject out of the upper edge crop.
- **Detailed Macro / Small Subject**: Increase `transform.scale: 1.30` to `1.65` combined with `x` and `y` offsets to emphasize details (faces, emblems, hands, small objects).

---

### Phase 6: Procedural Motion & Visual FX (`apply_visual_fx`)
Never leave still media motionless. Apply appropriate Visual FX based on narrative intent:
- **Continuous Cinematic Motion**: Apply `Slow Push-In` (`start_zoom: 1.0`, `target_zoom: 1.15 - 1.20`) or `Ken Burns` to create subtle motion across shots.
- **Dramatic Accents & Surprises**: Apply `Punch Zoom` (`start_zoom: 1.0`, `target_zoom: 1.5 - 1.7`, `duration: 0.4 - 0.6s`) timed to key revelations.
- **Action, Impacts & Chaos**: Apply `Camera Shake` (`intensity: 0.20 - 0.35`, `frequency: 12 - 16Hz`, `decay: "Exponential"`).

---

### Phase 7: Audio Bed & Sound Design
1. **Background Music (`audio_2`)**:
   Insert atmospheric music spanning the entire duration at `gain_db: -15.0`. Configure project settings:
   ```json
   {
     "auto_duck": true,
     "duck_amount_db": -11.0
   }
   ```
2. **Transition & Impact Sound Effects (`audio_3`)**:
   - **Transition SFX** (e.g., swooshes, whooshes, risers, page turns at `gain_db: -7.0` to `-5.0`) placed at scene cuts.
   - **Impact SFX** (e.g., bass drops, cinematic hits, stingers at `gain_db: -3.0` to `0.0`) placed at climax beats or surprising reveals.

---

### Phase 8: Caption Typography & Preset Selection (`set_caption_style`)
1. **Generate Word Cards**:
   Execute `generate_captions` headlessly with `words_per_card: 1` or `2` for high-retention pacing.
2. **Select Curated Typography Preset**:
   Choose the preset matching your video's genre:
   - `"crime_red"`: Bold Anton font, pure white with high-intensity crimson glow and crimson word highlight. *Best for true crime, mysteries, thrillers, and dark history.*
   - `"viral_yellow"`: Anton font, black outline with vibrant neon yellow glow and yellow highlight. *Best for high-energy hooks, TikTok trends, gaming, and lifestyle.*
   - `"cyber_cyan"`: Montserrat Bold, electric neon cyan glow and highlight. *Best for technology, AI, crypto, sci-fi, and futuristic topics.*
   - `"mrbeast_gold"`: Anton font, high-contrast gold text with heavy black drop shadow. *Best for finance, money, challenges, business, and luxury topics.*
   - `"clean_card"`: Poppins Bold, white text backed by a semi-transparent dark rounded backdrop card. *Best for podcasts, educational explainers, and corporate insights.*

---

## 4. Visual Verification & Framing Audit Checklist

Before declaring any automated editing task complete, perform this automated inspection loop:

1. **Check 3 Sample Timestamps via `seek` + `get_preview`**:
   - **Timestamp 1 (Hook ~0.5s)**: Verify hook visual is framed, watermark-free, and captions are centered.
   - **Timestamp 2 (Midpoint Action / Zoom Beat)**:
     - Is the primary subject actually visible and centered in the 9:16 vertical crop?
     - If the subject is cut off, adjust `transform.x` or `transform.y` and re-verify.
     - Ensure zoom effects do not introduce pixelation.
   - **Timestamp 3 (Climax / Reveal Beat)**: Verify visual punch aligns with caption reveal and audio stinger.
2. **Audit Audio Hierarchy**:
   - Confirm voiceover plays clearly over ducked background music.
3. **Verify Timeline Cleanliness via `get_timeline_summary`**:
   - Ensure all tracks (video, background, audio, music, SFX, captions) align and terminate together without trailing orphan clips.

---

## 5. Concrete Code Examples (Illustrative Scenarios Across Genres)

> [!IMPORTANT]
> The snippets below are concrete syntax examples for demonstration purposes across multiple different genres. When editing your project, replace the placeholder IDs, text, and parameters with your project's actual assets and story.

---

### Example Scenario 1: Science & Nature Explainer (Ocean Depths)

> [!NOTE]
> **Illustrative Example 1: Synthesizing Dialogue & Placing Foreground/Background Media**

```json
// Step 1: Synthesize voiceover for the hook
// Tool: synthesize_dialogue
{
  "text": "The deepest trench on Earth descends nearly seven miles into total darkness.",
  "voice": "adam-narrator",
  "start": 0.0,
  "track": "audio_1",
  "gain_db": 1.2
}

// Step 2: Insert dual-track vertical composited visuals
// Tool: apply_edits
{
  "operations": [
    {
      "op": "insert_clip",
      "media_id": "media_abyssal_trench_id",
      "track": "video_1",
      "start": 0.0,
      "duration": 5.4,
      "in_point": 1.0,
      "role": "background"
    },
    {
      "op": "insert_clip",
      "media_id": "media_abyssal_trench_id",
      "track": "video_2",
      "start": 0.0,
      "duration": 5.4,
      "in_point": 1.0,
      "role": "normal"
    }
  ]
}
```

---

### Example Scenario 2: Tech & Gaming Showcase (Submersible Drone / Off-Center Subject)

> [!NOTE]
> **Illustrative Example 2: Re-Centering an Off-Center Subject & Applying Motion**

```json
// Step 1: Shift framing rightward because the subject is framed on the left of 16:9 source
// Tool: apply_edits
{
  "operations": [
    {
      "op": "item_property",
      "item_id": "clip_submersible_fg_id",
      "property": "transform",
      "value": {
        "x": 0.28,
        "y": 0.06,
        "scale": 1.40
      }
    }
  ]
}

// Step 2: Apply smooth procedural push-in to maintain dynamic engagement
// Tool: apply_visual_fx
{
  "item_id": "clip_submersible_fg_id",
  "effect": "Slow Push-In",
  "properties": {
    "start_zoom": 1.0,
    "target_zoom": 1.18,
    "duration": 5.4,
    "easing": "Ease Out"
  }
}
```

---

### Example Scenario 3: Automated Captions & Style Selection

> [!NOTE]
> **Illustrative Example 3: Headless Word-by-Word Subtitles with Cyber Cyan Preset**

```json
// Step 1: Headlessly transcribe audio and generate word-by-word cards
// Tool: editor_command
{
  "command": "generate_captions",
  "arguments": {
    "headless": true,
    "words_per_card": 1
  }
}

// Step 2: Apply the cyber neon preset (suited for tech, sci-fi, science, or gaming)
// Tool: set_caption_style
{
  "preset": "cyber_cyan"
}
```

---

## 6. AI Asset Handling Rules (Mandatory Best Practices)

1. **Never Hardcode Media Filenames**: Never assume files like `hero_video.mp4`, `intro.png`, or historical case files exist in the project directory unless discovered dynamically via `get_timeline_summary` or `get_state`.
2. **Inspect Existing Tracks First**: Always query `get_timeline_summary` before writing new clips to avoid overwriting user edits or placing clips into non-existent tracks.
3. **Verify Audio Durations**: After generating speech via `synthesize_dialogue`, use the returned duration to set the end-times of matching B-roll and transition effects.
4. **Clean Termination**: Ensure that music beds, background blur layers, and subtitle sequences terminate precisely when the voiceover concludes.
