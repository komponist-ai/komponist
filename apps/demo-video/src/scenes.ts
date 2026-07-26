export const FPS = 30

export interface DemoScene {
  key: 'sources' | 'chat' | 'canvas' | 'workrooms' | 'compose'
  label: string
  title: string
  caption: string
  seconds: number
  focus: { x: number; y: number }
  zoom: number
}

export const INTRO_SECONDS = 5
export const OUTRO_SECONDS = 5

export const DEMO_SCENES: DemoScene[] = [
  {
    key: 'sources',
    label: '01 · Connect',
    title: 'Your knowledge is playing hide-and-seek.',
    caption: 'Komponist connects documents, Notion, and Slack, then turns the useful bits into reviewed facts with exact source passages.',
    seconds: 13,
    focus: { x: 0.66, y: 0.44 },
    zoom: 1.08,
  },
  {
    key: 'chat',
    label: '02 · Ask',
    title: 'Receipts, not confident vibes.',
    caption: 'A launch question returns confirmed blockers, owners, and citations—not a chatbot confidently improvising company policy.',
    seconds: 17,
    focus: { x: 0.66, y: 0.55 },
    zoom: 1.1,
  },
  {
    key: 'canvas',
    label: '03 · See',
    title: 'Ask an interface into existence.',
    caption: 'The same context becomes a live command center for deadlines, goals, decisions, relationships, and constraints.',
    seconds: 16,
    focus: { x: 0.68, y: 0.48 },
    zoom: 1.09,
  },
  {
    key: 'workrooms',
    label: '04 · Coordinate',
    title: 'The agents have adult supervision.',
    caption: 'A Workroom keeps the plan, agent progress, permission scope, and cited deliverables together, where people can steer and approve.',
    seconds: 16,
    focus: { x: 0.68, y: 0.5 },
    zoom: 1.08,
  },
  {
    key: 'compose',
    label: '05 · Present',
    title: 'Briefing assembled. Footnotes included.',
    caption: 'Compose produces a board-ready deliverable whose claims remain linked to reviewed company knowledge—even after the meeting ends.',
    seconds: 16,
    focus: { x: 0.69, y: 0.5 },
    zoom: 1.08,
  },
]

export const TOTAL_SECONDS = (
  INTRO_SECONDS
  + DEMO_SCENES.reduce((total, scene) => total + scene.seconds, 0)
  + OUTRO_SECONDS
)

export const TOTAL_FRAMES = TOTAL_SECONDS * FPS
