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

export type KomponistYCDemoProps = {
  voiceover: string | null
}

const ink = '#201c15'
const paper = '#f5ecdd'
const orange = '#e8641b'
const teal = '#0e8a7d'

const wordmark: React.CSSProperties = {
  fontFamily: 'Arial, Helvetica, sans-serif',
  fontWeight: 900,
  letterSpacing: '-0.055em',
}

const Monogram: React.FC<{ inverted?: boolean }> = ({ inverted = false }) => (
  <div
    style={{
      width: 82,
      height: 82,
      border: `4px solid ${inverted ? paper : ink}`,
      borderRadius: 20,
      display: 'grid',
      placeItems: 'center',
      color: inverted ? paper : ink,
      fontSize: 45,
      ...wordmark,
    }}
  >
    K
  </div>
)

const Intro: React.FC = () => {
  const frame = useCurrentFrame()
  const enter = spring({ frame, fps: FPS, config: { damping: 18, stiffness: 110 } })
  return (
    <AbsoluteFill style={{ background: ink, color: paper, padding: 110 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 28, opacity: enter }}>
        <Monogram inverted />
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

const BrowserFrame: React.FC<{ scene: DemoScene }> = ({ scene }) => {
  const frame = useCurrentFrame()
  const { durationInFrames } = useVideoConfig()
  const progress = interpolate(
    frame,
    [0, durationInFrames],
    [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) },
  )
  const scale = interpolate(progress, [0, 1], [1, scene.zoom])
  const cursorX = interpolate(progress, [0, 0.58, 1], [1030, scene.focus.x * 1600, scene.focus.x * 1600 + 24])
  const cursorY = interpolate(progress, [0, 0.58, 1], [740, scene.focus.y * 820, scene.focus.y * 820 - 16])
  return (
    <div
      style={{
        position: 'absolute',
        left: 160,
        top: 188,
        width: 1600,
        height: 820,
        border: `4px solid ${ink}`,
        borderRadius: 26,
        overflow: 'hidden',
        background: '#fff',
        boxShadow: `16px 16px 0 ${orange}`,
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
      <div style={{ position: 'relative', width: 1600, height: 778, overflow: 'hidden' }}>
        <Img
          src={staticFile(`captures/${scene.key}.png`)}
          style={{
            width: 1600,
            height: 1000,
            objectFit: 'cover',
            objectPosition: 'top',
            transform: `scale(${scale})`,
            transformOrigin: `${scene.focus.x * 100}% ${scene.focus.y * 100}%`,
          }}
        />
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
          }}
        />
      </div>
    </div>
  )
}

const ProductScene: React.FC<{ scene: DemoScene }> = ({ scene }) => {
  const frame = useCurrentFrame()
  const appear = spring({ frame, fps: FPS, config: { damping: 20 } })
  return (
    <AbsoluteFill style={{ background: paper, color: ink }}>
      <div style={{ position: 'absolute', left: 160, right: 160, top: 55, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div style={{ opacity: appear, transform: `translateY(${interpolate(appear, [0, 1], [24, 0])}px)` }}>
          <div style={{ color: orange, fontFamily: 'monospace', fontSize: 20, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase' }}>
            {scene.label}
          </div>
          <div style={{ marginTop: 10, fontSize: 54, ...wordmark }}>{scene.title}</div>
        </div>
        <div style={{ fontFamily: 'monospace', fontSize: 19, color: '#6e665c' }}>KOMPONIST / YC DEMO</div>
      </div>
      <BrowserFrame scene={scene} />
      <div
        style={{
          position: 'absolute',
          left: 260,
          right: 260,
          bottom: 32,
          minHeight: 82,
          border: `3px solid ${ink}`,
          borderRadius: 18,
          background: '#fffdf8',
          boxShadow: `7px 7px 0 ${teal}`,
          display: 'flex',
          alignItems: 'center',
          padding: '15px 28px',
          fontSize: 25,
          lineHeight: 1.34,
          fontWeight: 650,
        }}
      >
        {scene.caption}
      </div>
    </AbsoluteFill>
  )
}

const Outro: React.FC = () => {
  const frame = useCurrentFrame()
  const appear = spring({ frame, fps: FPS, config: { damping: 18 } })
  return (
    <AbsoluteFill style={{ background: orange, color: ink, padding: 110 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Monogram />
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

export const KomponistYCDemo: React.FC<KomponistYCDemoProps> = ({ voiceover }) => {
  let cursor = INTRO_SECONDS * FPS
  return (
    <AbsoluteFill>
      {voiceover ? <Html5Audio src={staticFile(voiceover)} /> : null}
      <Sequence durationInFrames={INTRO_SECONDS * FPS}>
        <Intro />
      </Sequence>
      {DEMO_SCENES.map((scene) => {
        const from = cursor
        const duration = scene.seconds * FPS
        cursor += duration
        return (
          <Sequence key={scene.key} from={from} durationInFrames={duration}>
            <ProductScene scene={scene} />
          </Sequence>
        )
      })}
      <Sequence from={(TOTAL_SECONDS - OUTRO_SECONDS) * FPS} durationInFrames={OUTRO_SECONDS * FPS}>
        <Outro />
      </Sequence>
    </AbsoluteFill>
  )
}
