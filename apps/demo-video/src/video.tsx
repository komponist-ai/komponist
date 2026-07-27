import React from 'react'
import {
  AbsoluteFill,
  Easing,
  Html5Audio,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion'
import {
  DEMO_SCENES,
  FPS,
  INTRO_SECONDS,
  OUTRO_SECONDS,
  TOTAL_SECONDS,
  type DemoScene,
} from './scenes'
import {
  DEFAULT_VOICEOVER_CAPTIONS,
  type VoiceoverCaption,
} from './voiceover'

export type KomponistYCDemoProps = {
  voiceover: string | null
  captions?: VoiceoverCaption[]
}

const ink = '#201c15'
const paper = '#f5ecdd'
const orange = '#e8641b'
const teal = '#0e8a7d'
const yellow = '#f2c14e'
const screenWidth = 1600
const screenHeight = 1000
const viewportHeight = 778
const cameraEase = Easing.bezier(0.22, 1, 0.36, 1)
const chatPrompt = 'What could block the Campus Forum launch, and who owns each blocker?'

const wordmark: React.CSSProperties = {
  fontFamily: 'Arial, Helvetica, sans-serif',
  fontWeight: 900,
  letterSpacing: '-0.055em',
}

const VideoBrandMark: React.FC<{
  inverted?: boolean
  size?: number
}> = ({ inverted = false, size = 86 }) => (
  <Img
    src={staticFile(inverted ? 'brand/logo-invers.svg' : 'brand/logo.svg')}
    style={{
      width: size,
      height: size,
      objectFit: 'contain',
    }}
  />
)

const VideoBrandTile: React.FC<{ size?: number }> = ({ size = 31 }) => (
  <Img
    src={staticFile('brand/icon.svg')}
    style={{
      width: size,
      height: size,
      borderRadius: Math.round(size * 0.25),
    }}
  />
)

const IntroGraph: React.FC<{ frame: number }> = ({ frame }) => {
  const nodes = [
    { label: 'DECISION', x: 1180, y: 185, color: yellow, delay: 5 },
    { label: 'GOAL', x: 1515, y: 320, color: teal, delay: 10 },
    { label: 'CONSTRAINT', x: 1220, y: 500, color: '#f5a66f', delay: 15 },
    { label: 'EVIDENCE', x: 1510, y: 650, color: paper, delay: 20 },
  ]
  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <svg width="1920" height="1080" style={{ position: 'absolute', inset: 0, opacity: 0.35 }}>
        {nodes.slice(1).map((node, index) => {
          const reveal = spring({ frame: frame - node.delay, fps: FPS, config: { damping: 20 } })
          return (
            <line
              key={node.label}
              x1={nodes[index].x + 80}
              y1={nodes[index].y + 22}
              x2={node.x + 80}
              y2={node.y + 22}
              stroke={paper}
              strokeWidth={3}
              strokeDasharray="8 10"
              pathLength={1}
              strokeDashoffset={1 - reveal}
            />
          )
        })}
      </svg>
      {nodes.map((node, index) => {
        const reveal = spring({ frame: frame - node.delay, fps: FPS, config: { damping: 14, stiffness: 130 } })
        const float = Math.sin((frame + index * 11) / 13) * 6
        return (
          <div
            key={node.label}
            style={{
              position: 'absolute',
              left: node.x,
              top: node.y,
              padding: '13px 20px',
              border: `3px solid ${paper}`,
              borderRadius: 999,
              background: node.color,
              color: node.color === teal ? '#fff' : ink,
              fontFamily: 'monospace',
              fontSize: 18,
              fontWeight: 800,
              letterSpacing: '0.08em',
              opacity: reveal,
              transform: `translateY(${(1 - reveal) * 30 + float}px) scale(${0.82 + reveal * 0.18})`,
              boxShadow: `7px 7px 0 ${orange}`,
            }}
          >
            {node.label}
          </div>
        )
      })}
    </div>
  )
}

const Intro: React.FC = () => {
  const frame = useCurrentFrame()
  const enter = spring({ frame, fps: FPS, config: { damping: 18, stiffness: 110 } })
  return (
    <AbsoluteFill
      style={{
        backgroundColor: ink,
        backgroundImage: `linear-gradient(rgba(245,236,221,.055) 2px, transparent 2px), linear-gradient(90deg, rgba(245,236,221,.055) 2px, transparent 2px)`,
        backgroundSize: '64px 64px',
        color: paper,
        overflow: 'hidden',
        padding: 110,
      }}
    >
      <IntroGraph frame={frame} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 28, opacity: enter }}>
        <VideoBrandMark inverted />
        <div style={{ fontSize: 58, ...wordmark }}>Komponist</div>
      </div>
      <div
        style={{
          marginTop: 'auto',
          maxWidth: 1480,
          transform: `translateY(${interpolate(enter, [0, 1], [45, 0])}px)`,
          opacity: enter,
        }}
      >
        <div style={{ color: orange, fontFamily: 'monospace', fontSize: 24, letterSpacing: '0.16em', textTransform: 'uppercase' }}>
          One shared context layer
        </div>
        <div style={{ marginTop: 28, fontSize: 104, lineHeight: 0.96, ...wordmark }}>
          Stop making people<br />and agents guess.
        </div>
      </div>
    </AbsoluteFill>
  )
}

function interpolateTrack(
  frame: number,
  durationInFrames: number,
  points: Array<{ at: number }>,
  values: number[],
) {
  return interpolate(
    frame,
    points.map((point) => point.at * Math.max(1, durationInFrames - 1)),
    values,
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: cameraEase,
    },
  )
}

function cameraOffset(
  viewportSize: number,
  contentSize: number,
  focus: number,
  zoom: number,
) {
  const scaledSize = contentSize * zoom
  if (scaledSize <= viewportSize) return (viewportSize - scaledSize) / 2
  return Math.min(0, Math.max(viewportSize - scaledSize, viewportSize / 2 - focus * scaledSize))
}

const ClickRipples: React.FC<{
  scene: DemoScene
  frame: number
  durationInFrames: number
}> = ({ scene, frame, durationInFrames }) => (
  <>
    {scene.cursor.filter((point) => point.click).map((point) => {
      const clickFrame = point.at * durationInFrames
      const age = frame - clickFrame
      if (age < 0 || age > 22) return null
      const progress = age / 22
      return (
        <div
          key={`${point.at}-${point.x}-${point.y}`}
          style={{
            position: 'absolute',
            left: point.x * screenWidth,
            top: point.y * screenHeight,
            width: 24 + progress * 74,
            height: 24 + progress * 74,
            border: `5px solid ${orange}`,
            borderRadius: '50%',
            opacity: 1 - progress,
            transform: 'translate(-50%, -50%)',
            boxShadow: `0 0 0 7px rgba(232,100,27,${0.18 * (1 - progress)})`,
          }}
        />
      )
    })}
  </>
)

const TypewriterPrompt: React.FC<{
  frame: number
  durationInFrames: number
  swapAt: number
}> = ({ frame, durationInFrames, swapAt }) => {
  const start = durationInFrames * 0.14
  const end = durationInFrames * 0.42
  const characters = Math.floor(interpolate(
    frame,
    [start, end],
    [0, chatPrompt.length],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.linear },
  ))
  const opacity = interpolate(
    frame,
    [start - 5, start + 4, swapAt * durationInFrames + 4],
    [0, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  )
  const cursorVisible = Math.floor(frame / 9) % 2 === 0
  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: 675,
          top: 907,
          width: 700,
          height: 48,
          display: 'flex',
          alignItems: 'center',
          overflow: 'hidden',
          background: '#fff',
          color: '#3f3931',
          fontFamily: 'Arial, Helvetica, sans-serif',
          fontSize: 16,
          lineHeight: 1.25,
          opacity,
          whiteSpace: 'nowrap',
        }}
      >
        {chatPrompt.slice(0, characters)}
        <span style={{ marginLeft: 2, width: 2, height: 22, background: orange, opacity: cursorVisible ? 1 : 0 }} />
      </div>
      {frame > durationInFrames * 0.44 && frame < durationInFrames * (swapAt + 0.06) ? (
        <div
          style={{
            position: 'absolute',
            left: 1030,
            top: 820,
            border: `2px solid ${ink}`,
            borderRadius: 999,
            background: paper,
            padding: '11px 17px',
            color: ink,
            fontFamily: 'monospace',
            fontSize: 14,
            fontWeight: 800,
            boxShadow: `4px 4px 0 ${teal}`,
          }}
        >
          SEARCHING 11 REVIEWED FACTS
          <span style={{ color: orange }}> ···</span>
        </div>
      ) : null}
    </>
  )
}

const BrowserFrame: React.FC<{ scene: DemoScene }> = ({ scene }) => {
  const frame = useCurrentFrame()
  const { durationInFrames } = useVideoConfig()
  const focusX = interpolateTrack(
    frame,
    durationInFrames,
    scene.camera,
    scene.camera.map((point) => point.x),
  )
  const focusY = interpolateTrack(
    frame,
    durationInFrames,
    scene.camera,
    scene.camera.map((point) => point.y),
  )
  const zoom = interpolateTrack(
    frame,
    durationInFrames,
    scene.camera,
    scene.camera.map((point) => point.zoom),
  )
  const cursorX = interpolateTrack(
    frame,
    durationInFrames,
    scene.cursor,
    scene.cursor.map((point) => point.x * screenWidth),
  )
  const cursorY = interpolateTrack(
    frame,
    durationInFrames,
    scene.cursor,
    scene.cursor.map((point) => point.y * screenHeight),
  )
  const enter = spring({
    frame,
    fps: FPS,
    durationInFrames: 28,
    config: { damping: 17, stiffness: 115, mass: 0.75 },
  })
  const exit = interpolate(
    frame,
    [durationInFrames - 14, durationInFrames - 1],
    [1, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.in(Easing.cubic),
    },
  )
  const panX = cameraOffset(screenWidth, screenWidth, focusX, zoom) + Math.sin(frame / 21) * 2
  const panY = cameraOffset(viewportHeight, screenHeight, focusY, zoom) + Math.cos(frame / 24) * 2
  const swap = scene.swapAt
    ? interpolate(
        frame,
        [scene.swapAt * durationInFrames - 6, scene.swapAt * durationInFrames + 9],
        [0, 1],
        {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: cameraEase,
        },
      )
    : 1
  const clickPulse = scene.cursor
    .filter((point) => point.click)
    .reduce((value, point) => {
      const distance = Math.abs(frame - point.at * durationInFrames)
      return Math.max(value, distance < 6 ? 1 - distance / 6 : 0)
    }, 0)

  return (
    <div
      style={{
        position: 'absolute',
        left: 160,
        top: 188,
        width: screenWidth,
        height: 820,
        border: `4px solid ${ink}`,
        borderRadius: 26,
        overflow: 'hidden',
        background: '#fff',
        boxShadow: `16px 16px 0 ${orange}`,
        opacity: enter * exit,
        transform: `translateY(${(1 - enter) * 54 + (1 - exit) * 20}px) scale(${0.96 + enter * 0.04})`,
      }}
    >
      <div style={{ height: 42, background: ink, display: 'flex', alignItems: 'center', gap: 9, paddingLeft: 18 }}>
        {[orange, '#f2c14e', teal].map((color) => (
          <span key={color} style={{ width: 12, height: 12, borderRadius: '50%', background: color }} />
        ))}
        <span style={{ marginLeft: 18, color: '#fff9', fontFamily: 'monospace', fontSize: 15 }}>
          komponist.build/{scene.key}
        </span>
      </div>
      <div style={{ position: 'relative', width: screenWidth, height: viewportHeight, overflow: 'hidden' }}>
        <div
          style={{
            position: 'absolute',
            left: panX,
            top: panY,
            width: screenWidth,
            height: screenHeight,
            transform: `scale(${zoom})`,
            transformOrigin: '0 0',
          }}
        >
          {scene.beforeImage ? (
            <Img
              src={staticFile(`captures/${scene.beforeImage}.png`)}
              style={{ position: 'absolute', inset: 0, width: screenWidth, height: screenHeight, opacity: 1 - swap }}
            />
          ) : null}
          <Img
            src={staticFile(`captures/${scene.key}.png`)}
            style={{ position: 'absolute', inset: 0, width: screenWidth, height: screenHeight, opacity: swap }}
          />
          {scene.key === 'chat' && scene.swapAt ? (
            <TypewriterPrompt frame={frame} durationInFrames={durationInFrames} swapAt={scene.swapAt} />
          ) : null}
          <ClickRipples scene={scene} frame={frame} durationInFrames={durationInFrames} />
          <div
            style={{
              position: 'absolute',
              left: cursorX,
              top: cursorY,
              width: 27,
              height: 34,
              background: '#fff',
              border: `3px solid ${ink}`,
              clipPath: 'polygon(0 0, 100% 65%, 58% 69%, 77% 100%, 57% 100%, 40% 72%, 0 100%)',
              filter: 'drop-shadow(2px 3px 0 rgba(32,28,21,.28))',
              transform: `translate(-3px, -3px) scale(${1 - clickPulse * 0.16})`,
            }}
          />
        </div>
      </div>
    </div>
  )
}

const SceneWipe: React.FC<{ frame: number; color: string }> = ({ frame, color }) => {
  const layers = [ink, orange, color]
  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 20, pointerEvents: 'none' }}>
      {layers.map((layer, index) => {
        const movement = interpolate(
          frame,
          [index * 3, 17 + index * 3],
          [0, -112],
          {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: cameraEase,
          },
        )
        return (
          <div
            key={`${layer}-${index}`}
            style={{
              position: 'absolute',
              inset: '-4%',
              background: layer,
              clipPath: 'polygon(0 0, 94% 0, 100% 100%, 0 100%)',
              transform: `translateX(${movement}%)`,
            }}
          />
        )
      })}
    </div>
  )
}

const AnimatedTitle: React.FC<{ title: string; frame: number }> = ({ title, frame }) => (
  <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: '0 13px', fontSize: 54, ...wordmark }}>
    {title.split(' ').map((word, index) => {
      const reveal = spring({
        frame: frame - index * 2,
        fps: FPS,
        config: { damping: 16, stiffness: 150, mass: 0.65 },
      })
      return (
        <span
          key={`${word}-${index}`}
          style={{
            display: 'inline-block',
            opacity: reveal,
            transform: `translateY(${(1 - reveal) * 24}px) rotate(${(1 - reveal) * -2}deg)`,
          }}
        >
          {word}
        </span>
      )
    })}
  </div>
)

const ProductScene: React.FC<{ scene: DemoScene; index: number }> = ({ scene, index }) => {
  const frame = useCurrentFrame()
  const { durationInFrames } = useVideoConfig()
  const appear = spring({ frame, fps: FPS, config: { damping: 20 } })
  const progress = interpolate(
    frame,
    [0, durationInFrames - 1],
    [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  )
  const accent = index % 2 ? teal : yellow
  return (
    <AbsoluteFill
      style={{
        backgroundColor: paper,
        backgroundImage: `radial-gradient(circle at 15% 20%, rgba(232,100,27,.08), transparent 24%), radial-gradient(circle at 90% 80%, rgba(14,138,125,.08), transparent 22%)`,
        color: ink,
        overflow: 'hidden',
      }}
    >
      <div style={{ position: 'absolute', left: 160, right: 160, top: 55, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div style={{ opacity: appear, transform: `translateY(${interpolate(appear, [0, 1], [24, 0])}px)` }}>
          <div style={{ color: orange, fontFamily: 'monospace', fontSize: 20, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase' }}>
            {scene.label}
          </div>
          <AnimatedTitle title={scene.title} frame={frame - 5} />
        </div>
        <div style={{ fontFamily: 'monospace', fontSize: 19, color: '#6e665c' }}>KOMPONIST / YC DEMO</div>
      </div>
      <BrowserFrame scene={scene} />
      <div
        style={{
          position: 'absolute',
          left: 0,
          bottom: 0,
          width: `${progress * 100}%`,
          height: 7,
          background: accent,
        }}
      />
      <SceneWipe frame={frame} color={accent} />
    </AbsoluteFill>
  )
}

const VoiceoverSubtitles: React.FC<{ captions: VoiceoverCaption[] }> = ({ captions }) => {
  const frame = useCurrentFrame()
  const time = frame / FPS
  const cue = captions.find((caption) => time >= caption.start && time < caption.end)
  if (!cue) return null

  const cueFrame = frame - cue.start * FPS
  const cueDuration = Math.max(1, (cue.end - cue.start) * FPS)
  const enter = spring({
    frame: cueFrame,
    fps: FPS,
    durationInFrames: 12,
    config: { damping: 18, stiffness: 155, mass: 0.65 },
  })
  const exit = interpolate(
    cueFrame,
    [cueDuration - 7, cueDuration],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  )
  const words = cue.words || cue.text.split(/\s+/).map((word, index, all) => ({
    text: word,
    start: cue.start + (cue.end - cue.start) * index / all.length,
    end: cue.start + (cue.end - cue.start) * (index + 1) / all.length,
  }))
  const currentWord = words.findIndex((word) => time >= word.start && time < word.end)

  return (
    <div
      style={{
        position: 'absolute',
        zIndex: 60,
        left: '50%',
        bottom: 34,
        width: 'fit-content',
        maxWidth: 1450,
        transform: `translate(-50%, ${(1 - enter) * 34}px) scale(${0.96 + enter * 0.04})`,
        opacity: enter * exit,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 9,
          flexWrap: 'wrap',
          border: `3px solid ${paper}`,
          borderRadius: 22,
          background: 'rgba(32,28,21,.95)',
          boxShadow: `9px 9px 0 ${orange}`,
          padding: '16px 28px 17px',
          color: paper,
          fontFamily: 'Arial, Helvetica, sans-serif',
          fontSize: 31,
          fontWeight: 760,
          lineHeight: 1.16,
          textAlign: 'center',
        }}
      >
        <span
          style={{
            width: 31,
            height: 31,
            marginRight: 7,
            display: 'grid',
            placeItems: 'center',
            borderRadius: 8,
            boxShadow: `2px 2px 0 ${orange}`,
            overflow: 'hidden',
          }}
        >
          <VideoBrandTile />
        </span>
        {words.map((word, index) => {
          const isCurrent = index === currentWord
          const isSpoken = time >= word.end
          return (
            <span
              key={`${word.text}-${index}`}
              style={{
                color: isCurrent ? yellow : isSpoken ? paper : 'rgba(245,236,221,.5)',
                transform: isCurrent ? 'translateY(-2px)' : undefined,
              }}
            >
              {word.text}
            </span>
          )
        })}
      </div>
    </div>
  )
}

const Outro: React.FC = () => {
  const frame = useCurrentFrame()
  const appear = spring({ frame, fps: FPS, config: { damping: 18 } })
  return (
    <AbsoluteFill style={{ background: orange, color: ink, padding: 110 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <VideoBrandMark />
        <div style={{ fontFamily: 'monospace', fontSize: 22, fontWeight: 700 }}>komponist.build</div>
      </div>
      <div style={{ marginTop: 'auto', opacity: appear, transform: `translateY(${interpolate(appear, [0, 1], [35, 0])}px)` }}>
        <div style={{ fontSize: 103, lineHeight: 0.95, maxWidth: 1500, ...wordmark }}>
          One shared, trusted context<br />for people and AI.
        </div>
        <div style={{ marginTop: 38, fontSize: 30, fontWeight: 700 }}>
          Open source · permission-aware · cited by default
        </div>
      </div>
    </AbsoluteFill>
  )
}

export const KomponistYCDemo: React.FC<KomponistYCDemoProps> = ({
  voiceover,
  captions = DEFAULT_VOICEOVER_CAPTIONS,
}) => {
  let cursor = INTRO_SECONDS * FPS
  return (
    <AbsoluteFill>
      {voiceover ? <Html5Audio src={staticFile(voiceover)} /> : null}
      <Sequence durationInFrames={INTRO_SECONDS * FPS}>
        <Intro />
      </Sequence>
      {DEMO_SCENES.map((scene, index) => {
        const from = cursor
        const duration = scene.seconds * FPS
        cursor += duration
        return (
          <Sequence key={scene.key} from={from} durationInFrames={duration}>
            <ProductScene scene={scene} index={index} />
          </Sequence>
        )
      })}
      <Sequence from={(TOTAL_SECONDS - OUTRO_SECONDS) * FPS} durationInFrames={OUTRO_SECONDS * FPS}>
        <Outro />
      </Sequence>
      <VoiceoverSubtitles captions={captions} />
    </AbsoluteFill>
  )
}
