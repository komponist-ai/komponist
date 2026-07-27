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
import type { KomponistYCDemoProps } from './video'

const ink = '#121318'
const orange = '#f16722'
const teal = '#22b7aa'
const paper = '#fffaf1'
const screenWidth = 1600
const screenHeight = 1000
const windowWidth = 1740
const windowHeight = 900
const chromeHeight = 46
const viewportHeight = windowHeight - chromeHeight
const cameraEase = Easing.bezier(0.22, 1, 0.36, 1)
const chatPrompt = 'What could block the Campus Forum launch, and who owns each blocker?'
const uiType = 'Arial, Helvetica, sans-serif'

const palettes = [
  ['#0879f9', '#5bc9ff', '#f7fbff'],
  ['#6264f5', '#8ec5ff', '#e9efff'],
  ['#08a992', '#76e4cf', '#f0fff9'],
  ['#865ce8', '#c4a8ff', '#f8f3ff'],
  ['#ee6b2b', '#ffc28b', '#fff6ec'],
] as const

const brandType: React.CSSProperties = {
  fontFamily: uiType,
  fontWeight: 900,
  letterSpacing: '-0.055em',
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

const BrandMark: React.FC<{ inverted?: boolean; size?: number }> = ({
  inverted = false,
  size = 58,
}) => (
  <Img
    src={staticFile(inverted ? 'brand/logo-invers.svg' : 'brand/logo.svg')}
    style={{ width: size, height: size, objectFit: 'contain' }}
  />
)

const AmbientBackdrop: React.FC<{
  palette: readonly [string, string, string]
  frame: number
}> = ({ palette, frame }) => {
  const drift = Math.sin(frame / 90) * 5
  const counterDrift = Math.cos(frame / 110) * 6
  return (
    <AbsoluteFill
      style={{
        overflow: 'hidden',
        background: `
          radial-gradient(circle at ${18 + drift}% ${18 + counterDrift}%, ${palette[1]} 0%, transparent 32%),
          radial-gradient(circle at ${86 - drift}% ${77 - counterDrift}%, ${palette[0]} 0%, transparent 38%),
          linear-gradient(135deg, ${palette[2]} 0%, ${palette[1]} 52%, ${palette[0]} 100%)
        `,
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: -180 + drift * 5,
          bottom: -220,
          width: 760,
          height: 420,
          borderRadius: '50%',
          background: 'rgba(255,255,255,.58)',
          filter: 'blur(42px)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          right: -120 - counterDrift * 5,
          top: -170,
          width: 620,
          height: 360,
          borderRadius: '50%',
          background: 'rgba(255,255,255,.42)',
          filter: 'blur(55px)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          opacity: 0.1,
          backgroundImage: 'radial-gradient(rgba(255,255,255,.9) 1px, transparent 1px)',
          backgroundSize: '22px 22px',
        }}
      />
    </AbsoluteFill>
  )
}

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
    [start - 5, start + 4, swapAt * durationInFrames + 8, swapAt * durationInFrames + 10],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  )
  const cursorVisible = Math.floor(frame / 9) % 2 === 0
  return (
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
      <span
        style={{
          marginLeft: 2,
          width: 2,
          height: 22,
          background: orange,
          opacity: cursorVisible ? 1 : 0,
        }}
      />
    </div>
  )
}

const CursorShape: React.FC<{
  x: number
  y: number
  opacity: number
  scale?: number
  blur?: number
}> = ({ x, y, opacity, scale = 1, blur = 0 }) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      width: 29,
      height: 38,
      background: '#fff',
      border: `3px solid ${ink}`,
      clipPath: 'polygon(0 0, 100% 65%, 58% 69%, 77% 100%, 57% 100%, 40% 72%, 0 100%)',
      filter: `drop-shadow(2px 4px 0 rgba(18,19,24,.28)) blur(${blur}px)`,
      opacity,
      transform: `translate(-3px, -3px) scale(${scale})`,
      transformOrigin: 'top left',
    }}
  />
)

const FloatingRecording: React.FC<{
  scene: DemoScene
  index: number
}> = ({ scene, index }) => {
  const frame = useCurrentFrame()
  const { durationInFrames } = useVideoConfig()
  const baseZoom = windowWidth / screenWidth
  const focusX = interpolateTrack(frame, durationInFrames, scene.camera, scene.camera.map(point => point.x))
  const focusY = interpolateTrack(frame, durationInFrames, scene.camera, scene.camera.map(point => point.y))
  const sceneZoom = interpolateTrack(frame, durationInFrames, scene.camera, scene.camera.map(point => point.zoom))
  const zoom = baseZoom * sceneZoom
  const cursorAt = (sampleFrame: number) => ({
    x: interpolateTrack(sampleFrame, durationInFrames, scene.cursor, scene.cursor.map(point => point.x * screenWidth)),
    y: interpolateTrack(sampleFrame, durationInFrames, scene.cursor, scene.cursor.map(point => point.y * screenHeight)),
  })
  const cursor = cursorAt(frame)
  const cursorTrail = [cursorAt(frame - 3), cursorAt(frame - 6), cursorAt(frame - 9)]
  const clickPulse = scene.cursor
    .filter(point => point.click)
    .reduce((value, point) => {
      const distance = Math.abs(frame - point.at * durationInFrames)
      return Math.max(value, distance < 8 ? 1 - distance / 8 : 0)
    }, 0)
  const entry = spring({
    frame,
    fps: FPS,
    durationInFrames: 30,
    config: { damping: 18, stiffness: 105, mass: 0.8 },
  })
  const exit = interpolate(
    frame,
    [durationInFrames - 16, durationInFrames - 1],
    [1, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.in(Easing.cubic),
    },
  )
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
  const panX = cameraOffset(windowWidth, screenWidth, focusX, zoom)
  const panY = cameraOffset(viewportHeight, screenHeight, focusY, zoom)
  const float = Math.sin((frame + index * 17) / 34) * 4
  const tilt = Math.sin((frame + index * 23) / 80) * 0.35

  return (
    <div
      style={{
        position: 'absolute',
        left: 90,
        top: 54,
        width: windowWidth,
        height: windowHeight,
        overflow: 'hidden',
        border: '1px solid rgba(255,255,255,.72)',
        borderRadius: 28,
        background: '#fff',
        boxShadow: '0 42px 95px rgba(5,25,62,.30), 0 12px 34px rgba(5,25,62,.18)',
        opacity: entry * exit,
        transform: `
          perspective(1800px)
          translateY(${(1 - entry) * 48 + float}px)
          rotateX(${0.35 - tilt * 0.25}deg)
          rotateY(${tilt}deg)
          scale(${0.965 + entry * 0.035 + clickPulse * 0.004})
        `,
      }}
    >
      <div
        style={{
          height: chromeHeight,
          display: 'grid',
          gridTemplateColumns: '1fr auto 1fr',
          alignItems: 'center',
          padding: '0 18px',
          borderBottom: '1px solid #e8e9ed',
          background: 'rgba(255,255,255,.96)',
          color: ink,
          fontFamily: 'Arial, Helvetica, sans-serif',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {['#ff5f57', '#febc2e', '#28c840'].map(color => (
            <span key={color} style={{ width: 11, height: 11, borderRadius: '50%', background: color }} />
          ))}
          <div style={{ marginLeft: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            <BrandMark size={24} />
            <span style={{ fontSize: 13, fontWeight: 800 }}>Komponist</span>
          </div>
        </div>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#777b86' }}>
          komponist.build/{scene.key}
        </div>
        <div style={{ justifySelf: 'end', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span
            style={{
              padding: '5px 9px',
              borderRadius: 999,
              background: '#f0f2f6',
              color: '#60646f',
              fontFamily: 'monospace',
              fontSize: 10,
              fontWeight: 800,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
            }}
          >
            {scene.label}
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 800 }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#ff4d4d' }} />
            REC
          </span>
        </div>
      </div>

      <div style={{ position: 'relative', width: windowWidth, height: viewportHeight, overflow: 'hidden' }}>
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

          {cursorTrail.map((trail, trailIndex) => (
            <CursorShape
              key={trailIndex}
              x={trail.x}
              y={trail.y}
              opacity={0.13 - trailIndex * 0.03}
              scale={1 - trailIndex * 0.06}
              blur={0.35 + trailIndex * 0.25}
            />
          ))}
          <CursorShape
            x={cursor.x}
            y={cursor.y}
            opacity={1}
            scale={1 - clickPulse * 0.14}
          />

          {scene.cursor.filter(point => point.click).map(point => {
            const age = frame - point.at * durationInFrames
            if (age < 0 || age > 22) return null
            const progress = age / 22
            return (
              <div
                key={`${point.at}-${point.x}`}
                style={{
                  position: 'absolute',
                  left: point.x * screenWidth,
                  top: point.y * screenHeight,
                  width: 20 + progress * 80,
                  height: 20 + progress * 80,
                  border: `4px solid ${orange}`,
                  borderRadius: '50%',
                  opacity: 1 - progress,
                  transform: 'translate(-50%, -50%)',
                  boxShadow: `0 0 0 8px rgba(241,103,34,${0.16 * (1 - progress)})`,
                }}
              />
            )
          })}
        </div>
      </div>
    </div>
  )
}

const SceneLabel: React.FC<{ scene: DemoScene; frame: number }> = ({ scene, frame }) => {
  const appear = spring({
    frame: frame - 8,
    fps: FPS,
    config: { damping: 18, stiffness: 130, mass: 0.7 },
  })
  return (
    <div
      style={{
        position: 'absolute',
        left: 134,
        top: 82,
        zIndex: 30,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '9px 14px',
        border: '1px solid rgba(255,255,255,.68)',
        borderRadius: 999,
        background: 'rgba(14,18,29,.80)',
        boxShadow: '0 12px 32px rgba(10,18,38,.24)',
        color: '#fff',
        fontFamily: 'Arial, Helvetica, sans-serif',
        opacity: appear,
        transform: `translateY(${(1 - appear) * 14}px)`,
      }}
    >
      <span style={{ color: '#ff9a61', fontFamily: 'monospace', fontSize: 12, fontWeight: 900 }}>
        {scene.label}
      </span>
      <span style={{ width: 1, height: 15, background: 'rgba(255,255,255,.25)' }} />
      <span style={{ fontSize: 15, fontWeight: 800 }}>{scene.title}</span>
    </div>
  )
}

const SceneWipe: React.FC<{ frame: number; color: string }> = ({ frame, color }) => {
  const movement = interpolate(
    frame,
    [0, 20],
    [0, 110],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: cameraEase,
    },
  )
  return (
    <div
      style={{
        position: 'absolute',
        zIndex: 80,
        inset: '-5%',
        background: color,
        clipPath: 'polygon(0 0, 100% 0, 93% 100%, 0 100%)',
        transform: `translateX(${movement}%)`,
      }}
    />
  )
}

const RecordlyScene: React.FC<{ scene: DemoScene; index: number }> = ({ scene, index }) => {
  const frame = useCurrentFrame()
  const palette = palettes[index % palettes.length]
  return (
    <AbsoluteFill>
      <AmbientBackdrop palette={palette} frame={frame} />
      <FloatingRecording scene={scene} index={index} />
      <SceneLabel scene={scene} frame={frame} />
      <SceneWipe frame={frame} color={palette[0]} />
    </AbsoluteFill>
  )
}

const GlassSubtitles: React.FC<{ captions: VoiceoverCaption[] }> = ({ captions }) => {
  const frame = useCurrentFrame()
  const time = frame / FPS
  const cue = captions.find(caption => time >= caption.start && time < caption.end)
  if (!cue) return null

  const cueFrame = frame - cue.start * FPS
  const cueDuration = Math.max(1, (cue.end - cue.start) * FPS)
  const appear = spring({
    frame: cueFrame,
    fps: FPS,
    durationInFrames: 10,
    config: { damping: 20, stiffness: 160, mass: 0.65 },
  })
  const exit = interpolate(
    cueFrame,
    [cueDuration - 6, cueDuration],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  )
  const words = cue.words || cue.text.split(/\s+/).map((word, index, all) => ({
    text: word,
    start: cue.start + (cue.end - cue.start) * index / all.length,
    end: cue.start + (cue.end - cue.start) * (index + 1) / all.length,
  }))
  const currentWord = words.findIndex(word => time >= word.start && time < word.end)

  return (
    <div
      style={{
        position: 'absolute',
        zIndex: 100,
        left: '50%',
        bottom: 25,
        maxWidth: 1500,
        transform: `translate(-50%, ${(1 - appear) * 22}px) scale(${0.98 + appear * 0.02})`,
        opacity: appear * exit,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexWrap: 'wrap',
          gap: '0 8px',
          minHeight: 58,
          padding: '12px 24px',
          border: '1px solid rgba(255,255,255,.22)',
          borderRadius: 17,
          background: 'rgba(12,15,24,.88)',
          boxShadow: '0 18px 44px rgba(5,12,30,.28)',
          color: '#fff',
          fontFamily: 'Arial, Helvetica, sans-serif',
          fontSize: 27,
          fontWeight: 760,
          lineHeight: 1.16,
          textAlign: 'center',
        }}
      >
        <BrandMark inverted size={27} />
        {words.map((word, index) => (
          <span
            key={`${word.text}-${index}`}
            style={{
              color: index === currentWord
                ? '#ff9a61'
                : time >= word.end
                  ? '#fff'
                  : 'rgba(255,255,255,.48)',
              transform: index === currentWord ? 'translateY(-1px)' : undefined,
            }}
          >
            {word.text}
          </span>
        ))}
      </div>
    </div>
  )
}

const RecordlyIntro: React.FC = () => {
  const frame = useCurrentFrame()
  const appear = spring({ frame, fps: FPS, config: { damping: 18, stiffness: 110 } })
  const preview = spring({
    frame: frame - 12,
    fps: FPS,
    config: { damping: 20, stiffness: 95, mass: 0.9 },
  })
  return (
    <AbsoluteFill>
      <AmbientBackdrop palette={palettes[0]} frame={frame} />
      <div
        style={{
          position: 'absolute',
          left: 140,
          top: 138,
          width: 720,
          color: '#fff',
          opacity: appear,
          transform: `translateY(${(1 - appear) * 28}px)`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <BrandMark inverted size={72} />
          <span style={{ fontSize: 54, ...brandType }}>Komponist</span>
        </div>
        <div style={{ marginTop: 74, fontSize: 86, lineHeight: 0.98, ...brandType }}>
          One shared context<br />for people and AI.
        </div>
        <div
          style={{
            marginTop: 30,
            color: 'rgba(255,255,255,.94)',
            fontFamily: uiType,
            fontSize: 28,
            fontWeight: 800,
            letterSpacing: '-0.022em',
            lineHeight: 1.15,
            textRendering: 'geometricPrecision',
            WebkitFontSmoothing: 'antialiased',
            textShadow: '0 2px 18px rgba(13,36,74,.18)',
          }}
        >
          Connected knowledge. Multiplayer agents. Dynamic interfaces.
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          right: -90,
          top: 118,
          width: 980,
          height: 720,
          overflow: 'hidden',
          border: '1px solid rgba(255,255,255,.7)',
          borderRadius: 30,
          background: '#fff',
          boxShadow: '0 42px 100px rgba(5,25,62,.34)',
          opacity: preview,
          transform: `perspective(1500px) translateX(${(1 - preview) * 80}px) rotateY(${-7 + preview * 3}deg) rotateX(1deg)`,
        }}
      >
        <Img
          src={staticFile('captures/canvas.png')}
          style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'left top' }}
        />
      </div>
    </AbsoluteFill>
  )
}

const RecordlyOutro: React.FC = () => {
  const frame = useCurrentFrame()
  const appear = spring({ frame, fps: FPS, config: { damping: 18, stiffness: 110 } })
  return (
    <AbsoluteFill>
      <AmbientBackdrop palette={palettes[4]} frame={frame} />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'grid',
          placeItems: 'center',
          color: '#fff',
          textAlign: 'center',
          opacity: appear,
          transform: `scale(${0.96 + appear * 0.04})`,
        }}
      >
        <div>
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 22 }}>
            <BrandMark inverted size={82} />
            <span style={{ fontSize: 64, ...brandType }}>Komponist</span>
          </div>
          <div style={{ marginTop: 56, fontSize: 82, lineHeight: 1, ...brandType }}>
            Knowledge stops hiding.<br />Work starts moving.
          </div>
          <div
            style={{
              display: 'inline-flex',
              marginTop: 42,
              padding: '13px 22px',
              border: '1px solid rgba(255,255,255,.28)',
              borderRadius: 999,
              background: 'rgba(12,15,24,.76)',
              fontFamily: 'monospace',
              fontSize: 22,
              fontWeight: 800,
            }}
          >
            komponist.build
          </div>
        </div>
      </div>
    </AbsoluteFill>
  )
}

export const KomponistRecordlyDemo: React.FC<KomponistYCDemoProps> = ({
  voiceover,
  captions = DEFAULT_VOICEOVER_CAPTIONS,
}) => {
  let cursor = INTRO_SECONDS * FPS
  return (
    <AbsoluteFill
      style={{
        background: ink,
        fontFamily: uiType,
        textRendering: 'geometricPrecision',
        WebkitFontSmoothing: 'antialiased',
      }}
    >
      {voiceover ? <Html5Audio src={staticFile(voiceover)} /> : null}
      <Sequence durationInFrames={INTRO_SECONDS * FPS}>
        <RecordlyIntro />
      </Sequence>
      {DEMO_SCENES.map((scene, index) => {
        const from = cursor
        const duration = scene.seconds * FPS
        cursor += duration
        return (
          <Sequence key={scene.key} from={from} durationInFrames={duration}>
            <RecordlyScene scene={scene} index={index} />
          </Sequence>
        )
      })}
      <Sequence from={(TOTAL_SECONDS - OUTRO_SECONDS) * FPS} durationInFrames={OUTRO_SECONDS * FPS}>
        <RecordlyOutro />
      </Sequence>
      <GlassSubtitles captions={captions} />
    </AbsoluteFill>
  )
}
