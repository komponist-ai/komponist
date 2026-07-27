import React from 'react'
import { Composition, type AnyZodObject } from 'remotion'
import { KomponistRecordlyDemo } from './recordly-video'
import { KomponistYCDemo, type KomponistYCDemoProps } from './video'
import { FPS, TOTAL_FRAMES } from './scenes'
import { DEFAULT_VOICEOVER_CAPTIONS } from './voiceover'

const defaultProps: KomponistYCDemoProps = {
  voiceover: null,
  captions: DEFAULT_VOICEOVER_CAPTIONS,
}

export const RemotionRoot: React.FC = () => (
  <>
    <Composition<AnyZodObject, KomponistYCDemoProps>
      id="KomponistYC"
      component={KomponistYCDemo}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={1920}
      height={1080}
      defaultProps={defaultProps}
    />
    <Composition<AnyZodObject, KomponistYCDemoProps>
      id="KomponistRecordly"
      component={KomponistRecordlyDemo}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={1920}
      height={1080}
      defaultProps={defaultProps}
    />
  </>
)
