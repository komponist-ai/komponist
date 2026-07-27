export interface VoiceoverWord {
  text: string
  start: number
  end: number
}

export interface VoiceoverCaption {
  start: number
  end: number
  text: string
  words?: VoiceoverWord[]
}

export interface VoiceoverSegment {
  key: 'intro' | 'sources' | 'chat' | 'canvas' | 'workrooms' | 'compose' | 'outro'
  start: number
  end: number
  captions: string[]
}

export const VOICEOVER_SEGMENTS: VoiceoverSegment[] = [
  {
    key: 'intro',
    start: 0.35,
    end: 4.8,
    captions: [
      'Meet Komponist:',
      'one shared context layer for humans and AI.',
    ],
  },
  {
    key: 'sources',
    start: 5.25,
    end: 17.7,
    captions: [
      'Company knowledge loves hide-and-seek.',
      'It hides in Slack, Notion, documents—',
      "and occasionally a teammate's head.",
      'Komponist connects it, extracts reviewed facts,',
      'and keeps the evidence attached.',
    ],
  },
  {
    key: 'chat',
    start: 18.25,
    end: 34.7,
    captions: [
      'CampusKollektiv is planning its Campus Forum.',
      'I ask what could block the launch.',
      'Komponist finds the unsigned data agreement,',
      'the volunteer deadline, and the budget ceiling.',
      'No confident chatbot improv—every answer brings receipts.',
    ],
  },
  {
    key: 'canvas',
    start: 35.25,
    end: 50.7,
    captions: [
      'Need a command center? Just ask.',
      'Canvas turns the same knowledge graph into a live interface',
      'for deadlines, decisions, owners, and blockers.',
      'No dashboard archaeology required.',
    ],
  },
  {
    key: 'workrooms',
    start: 51.25,
    end: 66.7,
    captions: [
      'Then people and agents continue in a shared Workroom.',
      'Agents research and draft inside permission-aware context.',
      'Humans can redirect, pause, and approve.',
      'In other words:',
      'the robots have adult supervision.',
    ],
  },
  {
    key: 'compose',
    start: 67.25,
    end: 82.7,
    captions: [
      'Finally, Compose turns the result into board-ready',
      'briefings, presentations, and summaries.',
      'It adapts the structure to its audience.',
      'Every claim stays linked to its source,',
      'so polished output never outruns the truth.',
    ],
  },
  {
    key: 'outro',
    start: 83.25,
    end: 87.7,
    captions: [
      'Komponist: knowledge stops hiding.',
      'Agents stop guessing. Work moves.',
    ],
  },
]

export const voiceoverText = (segment: VoiceoverSegment) => (
  segment.captions.join(' ')
)

export function defaultVoiceoverCaptions(): VoiceoverCaption[] {
  return VOICEOVER_SEGMENTS.flatMap((segment) => {
    const weights = segment.captions.map((caption) => (
      Math.max(1, caption.split(/\s+/).length)
    ))
    const totalWeight = weights.reduce((sum, weight) => sum + weight, 0)
    const duration = segment.end - segment.start
    let cursor = segment.start
    return segment.captions.map((text, index) => {
      const share = duration * (weights[index] / totalWeight)
      const start = cursor
      const end = index === segment.captions.length - 1
        ? segment.end
        : cursor + share
      cursor = end
      const tokens = text.match(/\S+/g) || []
      const wordDuration = (end - start) / Math.max(1, tokens.length)
      return {
        start,
        end,
        text,
        words: tokens.map((word, wordIndex) => ({
          text: word,
          start: start + wordIndex * wordDuration,
          end: start + (wordIndex + 1) * wordDuration,
        })),
      }
    })
  })
}

export const DEFAULT_VOICEOVER_CAPTIONS = defaultVoiceoverCaptions()
