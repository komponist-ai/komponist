export const FPS = 30

export interface MotionPoint {
  at: number
  x: number
  y: number
  zoom: number
}

export interface CursorPoint {
  at: number
  x: number
  y: number
  click?: boolean
}

export interface DemoScene {
  key: 'sources' | 'chat' | 'canvas' | 'workrooms' | 'compose'
  label: string
  title: string
  caption: string
  seconds: number
  camera: MotionPoint[]
  cursor: CursorPoint[]
  beforeImage?: string
  swapAt?: number
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
    beforeImage: 'sources-collapsed',
    swapAt: 0.27,
    camera: [
      { at: 0, x: 0.52, y: 0.38, zoom: 0.94 },
      { at: 0.18, x: 0.61, y: 0.44, zoom: 1.02 },
      { at: 0.46, x: 0.68, y: 0.55, zoom: 1.1 },
      { at: 0.82, x: 0.76, y: 0.64, zoom: 1.16 },
      { at: 1, x: 0.74, y: 0.6, zoom: 1.12 },
    ],
    cursor: [
      { at: 0, x: 0.78, y: 0.31 },
      { at: 0.2, x: 0.92, y: 0.45 },
      { at: 0.27, x: 0.92, y: 0.45, click: true },
      { at: 0.62, x: 0.62, y: 0.61 },
      { at: 0.84, x: 0.79, y: 0.71 },
    ],
  },
  {
    key: 'chat',
    label: '02 · Ask',
    title: 'Receipts, not confident vibes.',
    caption: 'A launch question returns confirmed blockers, owners, and citations—not a chatbot confidently improvising company policy.',
    seconds: 17,
    beforeImage: 'chat-empty',
    swapAt: 0.48,
    camera: [
      { at: 0, x: 0.55, y: 0.44, zoom: 0.94 },
      { at: 0.12, x: 0.7, y: 0.88, zoom: 1.06 },
      { at: 0.43, x: 0.74, y: 0.9, zoom: 1.1 },
      { at: 0.58, x: 0.72, y: 0.3, zoom: 1.06 },
      { at: 0.82, x: 0.74, y: 0.59, zoom: 1.12 },
      { at: 1, x: 0.7, y: 0.5, zoom: 1.08 },
    ],
    cursor: [
      { at: 0, x: 0.7, y: 0.72 },
      { at: 0.13, x: 0.71, y: 0.93 },
      { at: 0.39, x: 0.71, y: 0.93 },
      { at: 0.44, x: 0.91, y: 0.93 },
      { at: 0.47, x: 0.91, y: 0.93, click: true },
      { at: 0.64, x: 0.78, y: 0.36 },
      { at: 0.86, x: 0.74, y: 0.65 },
    ],
  },
  {
    key: 'canvas',
    label: '03 · See',
    title: 'Ask an interface into existence.',
    caption: 'The same context becomes a live command center for deadlines, goals, decisions, relationships, and constraints.',
    seconds: 16,
    camera: [
      { at: 0, x: 0.54, y: 0.38, zoom: 0.94 },
      { at: 0.2, x: 0.67, y: 0.36, zoom: 1.06 },
      { at: 0.58, x: 0.73, y: 0.49, zoom: 1.14 },
      { at: 0.86, x: 0.64, y: 0.75, zoom: 1.11 },
      { at: 1, x: 0.65, y: 0.68, zoom: 1.08 },
    ],
    cursor: [
      { at: 0, x: 0.64, y: 0.2 },
      { at: 0.32, x: 0.61, y: 0.39 },
      { at: 0.58, x: 0.84, y: 0.51 },
      { at: 0.62, x: 0.84, y: 0.51, click: true },
      { at: 0.84, x: 0.69, y: 0.77 },
    ],
  },
  {
    key: 'workrooms',
    label: '04 · Coordinate',
    title: 'The agents have adult supervision.',
    caption: 'A Workroom keeps the plan, agent progress, permission scope, and cited deliverables together, where people can steer and approve.',
    seconds: 16,
    camera: [
      { at: 0, x: 0.52, y: 0.35, zoom: 0.94 },
      { at: 0.2, x: 0.68, y: 0.2, zoom: 1.06 },
      { at: 0.52, x: 0.66, y: 0.51, zoom: 1.12 },
      { at: 0.8, x: 0.87, y: 0.36, zoom: 1.14 },
      { at: 1, x: 0.74, y: 0.46, zoom: 1.08 },
    ],
    cursor: [
      { at: 0, x: 0.63, y: 0.28 },
      { at: 0.27, x: 0.64, y: 0.12 },
      { at: 0.5, x: 0.61, y: 0.52 },
      { at: 0.73, x: 0.88, y: 0.31 },
      { at: 0.77, x: 0.88, y: 0.31, click: true },
    ],
  },
  {
    key: 'compose',
    label: '05 · Present',
    title: 'Briefing assembled. Footnotes included.',
    caption: 'Compose produces a board-ready deliverable whose claims remain linked to reviewed company knowledge—even after the meeting ends.',
    seconds: 16,
    camera: [
      { at: 0, x: 0.55, y: 0.35, zoom: 0.94 },
      { at: 0.2, x: 0.73, y: 0.35, zoom: 1.05 },
      { at: 0.55, x: 0.72, y: 0.6, zoom: 1.12 },
      { at: 0.82, x: 0.92, y: 0.13, zoom: 1.14 },
      { at: 1, x: 0.74, y: 0.44, zoom: 1.07 },
    ],
    cursor: [
      { at: 0, x: 0.68, y: 0.26 },
      { at: 0.35, x: 0.59, y: 0.78 },
      { at: 0.4, x: 0.59, y: 0.78, click: true },
      { at: 0.72, x: 0.9, y: 0.16 },
      { at: 0.8, x: 0.94, y: 0.04 },
    ],
  },
]

export const TOTAL_SECONDS = (
  INTRO_SECONDS
  + DEMO_SCENES.reduce((total, scene) => total + scene.seconds, 0)
  + OUTRO_SECONDS
)

export const TOTAL_FRAMES = TOTAL_SECONDS * FPS
