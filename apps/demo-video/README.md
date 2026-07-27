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

## Add the founder voice-over

Record the script below naturally and save it as
`apps/demo-video/public/voiceover.mp3`, then run:

```bash
npm run capture
npm run render:voice
```

The visual edit is 88 seconds. Use a warm, curious voice with dry confidence,
not an exaggerated announcer voice. Read at roughly 130 words per minute, leave
short pauses at scene changes, and give the punchlines a little room.

> Meet Komponist: the shared context layer for humans and AI.
>
> Most organizations already have a brain. It is just hiding across documents,
> Notion, Slack, and that one teammate who remembers everything. Komponist
> connects those sources, extracts decisions, goals, projects, and constraints,
> and keeps the exact evidence. Knowledge can stop playing hide-and-seek. It was
> getting suspiciously good at it.
>
> CampusKollektiv is planning its Campus Forum. I ask what could block the
> launch. Komponist answers directly: an unsigned data agreement, a volunteer
> deadline, and the budget ceiling. No confident chatbot improv. Every claim
> brings a receipt.
>
> Need a command center? Ask. Canvas turns the same knowledge graph into a live
> interface for deadlines, decisions, owners, and blockers. No dashboard
> archaeology required.
>
> Then people and agents continue in a shared Workroom. Agents research and
> draft inside permission-aware context; humans can steer, pause, and approve.
> The robots have adult supervision.
>
> Finally, Compose turns the result into a board-ready briefing, with every
> claim linked back to its source.
>
> That is Komponist: one shared, trusted context for people and AI—so knowledge
> stops hiding, agents stop guessing, and work actually moves.

## Edit before rendering

- Scene order and duration: `src/scenes.ts`
- Camera paths, cursor actions, and click timing: `src/scenes.ts`
- Visual treatment and interaction choreography: `src/video.tsx`
- Live capture behavior: `capture.ts`
- Interactive preview: `npm run studio`

Keep the separate YC founder introduction to one minute with only the founders
talking. This package is for the optional product demo.
