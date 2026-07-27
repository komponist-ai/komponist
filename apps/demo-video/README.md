# Komponist YC demo video

This package turns a real, authenticated CampusKollektiv workspace into a
repeatable 88-second product demo. Playwright captures deterministic before
and after product states; Remotion adds spring-driven camera paths, pans,
typed chat interaction, click ripples, branded transitions, captions, intro,
and end card.

## First setup

```bash
cd apps/demo-video
npm install
npx playwright install chromium
```

Run the Komponist web app and API, then create the silent captioned version:

```bash
npm run demo
```

The video is written to `apps/demo-video/out/komponist-yc-demo.mp4`.
To reuse an existing Google Chrome installation instead of Playwright's
Chromium, prefix the command with
`KOMPONIST_DEMO_BROWSER_CHANNEL=chrome`.

For a hosted deployment, provide a dedicated demo account:

```bash
KOMPONIST_DEMO_WEB_URL=https://komponist.build \
KOMPONIST_DEMO_API_URL=https://api.komponist.build \
KOMPONIST_DEMO_EMAIL=demo@komponist.build \
KOMPONIST_DEMO_PASSWORD='use-a-long-demo-password' \
npm run demo
```

The installer creates the organization as **CampusKollektiv** and installs
only the current Campus Forum sources, cited chat, Canvas, Workroom, and
Compose artifact. Re-running it is safe.

## Generate the timed ElevenLabs voice-over

The recommended path generates the narration scene by scene, reads
ElevenLabs' character timestamps, turns them into word-level subtitle timing,
and assembles one exactly 88-second audio track. Intentional pauses stay at the
scene changes. If a take runs a fraction too long, the script applies a small,
capped tempo correction instead of moving the visual edit.

Create a voice in ElevenLabs with a warm, curious, lightly mischievous delivery
rather than an announcer voice. Copy its voice ID, then run:

> Young European startup narrator, warm and intelligent, conversational and
> self-assured, with dry comedic timing and a subtle smile. Clear international
> English, medium-low pitch, crisp diction, natural pauses, never salesy or
> theatrical. Sounds like a clever product builder showing something they
> genuinely enjoy.

```bash
cd apps/demo-video
export ELEVENLABS_API_KEY='your-api-key'
export ELEVENLABS_VOICE_ID='your-voice-id'
npm run demo:elevenlabs
```

This captures the live product, generates `public/voiceover.mp3`, writes exact
caption timings to `voiceover-props.generated.json`, and renders the result to
`out/komponist-yc-demo.mp4`. The API key never belongs in the repository.

The defaults are deliberately expressive but controlled:

- model: `eleven_multilingual_v2`
- speed: `1.02`
- stability: `0.48`
- similarity: `0.78`
- style exaggeration: `0`

Override a value only if the chosen voice needs it:

```bash
ELEVENLABS_SPEED=1.06 ELEVENLABS_STABILITY=0.55 \
npm run demo:elevenlabs
```

If the screenshots are already current, skip the capture:

```bash
npm run voiceover:elevenlabs
npm run render:elevenlabs
```

## Narration script

The source of truth is `src/voiceover.ts`; its scene windows also drive the
fallback captions in silent renders.

> Meet Komponist: one shared context layer for humans and AI.
>
> Company knowledge loves hide-and-seek. It hides in Slack, Notion,
> documents—and occasionally a teammate's head. Komponist connects it,
> extracts reviewed facts, and keeps the evidence attached.
>
> CampusKollektiv is planning its Campus Forum. I ask what could block the
> launch. Komponist finds the unsigned data agreement, the volunteer deadline,
> and the budget ceiling. No confident chatbot improv—every answer brings
> receipts.
>
> Need a command center? Just ask. Canvas turns the same knowledge graph into a
> live interface for deadlines, decisions, owners, and blockers. No dashboard
> archaeology required.
>
> Then people and agents continue in a shared Workroom. Agents research and
> draft inside permission-aware context. Humans can redirect, pause, and
> approve. In other words: the robots have adult supervision.
>
> Finally, Compose turns the result into board-ready briefings, presentations,
> and summaries. It adapts the structure to its audience. Every claim stays
> linked to its source, so polished output never outruns the truth.
>
> Komponist: knowledge stops hiding. Agents stop guessing. Work moves.

## Use a manually recorded voice-over

Record the same script naturally and save it as
`apps/demo-video/public/voiceover.mp3`, then run:

```bash
npm run capture
npm run render:voice
```

The silent render still includes polished estimated subtitles. For a manually
recorded take, align it with ElevenLabs Forced Alignment (or another alignment
tool) and replace the estimated timings if word-perfect highlighting is
required.

## Edit before rendering

- Scene order and duration: `src/scenes.ts`
- Camera paths, cursor actions, and click timing: `src/scenes.ts`
- Visual treatment and interaction choreography: `src/video.tsx`
- Narration, scene windows, and subtitle copy: `src/voiceover.ts`
- ElevenLabs generation and audio fitting: `generate-voiceover.ts`
- Live capture behavior: `capture.ts`
- Interactive preview: `npm run studio`

Keep the separate YC founder introduction to one minute with only the founders
talking. This package is for the optional product demo.
