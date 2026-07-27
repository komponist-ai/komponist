import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'
import { TOTAL_SECONDS } from './src/scenes'
import {
  VOICEOVER_SEGMENTS,
  voiceoverText,
  type VoiceoverCaption,
  type VoiceoverSegment,
  type VoiceoverWord,
} from './src/voiceover'

interface ElevenLabsAlignment {
  characters: string[]
  character_start_times_seconds: number[]
  character_end_times_seconds: number[]
}

interface ElevenLabsTimingResponse {
  audio_base64: string
  alignment: ElevenLabsAlignment | null
  normalized_alignment: ElevenLabsAlignment | null
}

interface GeneratedSegment {
  segment: VoiceoverSegment
  path: string
  rawDuration: number
  tempo: number
  captions: VoiceoverCaption[]
}

const execute = promisify(execFile)
const here = dirname(fileURLToPath(import.meta.url))
const publicDirectory = resolve(here, 'public')
const apiKey = process.env.ELEVENLABS_API_KEY
const voiceId = process.env.ELEVENLABS_VOICE_ID
const modelId = process.env.ELEVENLABS_MODEL_ID || 'eleven_multilingual_v2'
const speed = Number(process.env.ELEVENLABS_SPEED || '1.02')
const stability = Number(process.env.ELEVENLABS_STABILITY || '0.48')
const similarity = Number(process.env.ELEVENLABS_SIMILARITY || '0.78')
const ffmpeg = process.env.FFMPEG_PATH || 'ffmpeg'

if (!apiKey || !voiceId) {
  throw new Error(
    'Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID before generating the voice-over.',
  )
}

if (speed < 0.7 || speed > 1.2) {
  throw new Error('ELEVENLABS_SPEED must be between 0.7 and 1.2.')
}

function captionsFromAlignment(
  segment: VoiceoverSegment,
  alignment: ElevenLabsAlignment,
  tempo: number,
): VoiceoverCaption[] {
  let offset = 0
  return segment.captions.map((text) => {
    const firstCharacter = offset
    const lastCharacter = offset + text.length - 1
    offset += text.length + 1
    const relativeStart = alignment.character_start_times_seconds[firstCharacter]
    const relativeEnd = alignment.character_end_times_seconds[lastCharacter]
    if (relativeStart === undefined || relativeEnd === undefined) {
      throw new Error(`ElevenLabs returned incomplete timing data for ${segment.key}.`)
    }
    const words: VoiceoverWord[] = []
    for (const match of text.matchAll(/\S+/g)) {
      const wordStart = firstCharacter + (match.index || 0)
      const wordEnd = wordStart + match[0].length - 1
      const start = alignment.character_start_times_seconds[wordStart]
      const end = alignment.character_end_times_seconds[wordEnd]
      if (start === undefined || end === undefined) {
        throw new Error(`ElevenLabs returned incomplete word timing data for ${segment.key}.`)
      }
      words.push({
        text: match[0],
        start: segment.start + start / tempo,
        end: segment.start + end / tempo,
      })
    }
    return {
      start: segment.start + relativeStart / tempo,
      end: segment.start + relativeEnd / tempo,
      text,
      words,
    }
  })
}

async function generateSegment(
  segment: VoiceoverSegment,
  index: number,
  directory: string,
): Promise<GeneratedSegment> {
  const response = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(voiceId!)}/with-timestamps?output_format=mp3_44100_128`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'xi-api-key': apiKey!,
      },
      body: JSON.stringify({
        text: voiceoverText(segment),
        model_id: modelId,
        previous_text: index > 0 ? voiceoverText(VOICEOVER_SEGMENTS[index - 1]) : undefined,
        next_text: index < VOICEOVER_SEGMENTS.length - 1
          ? voiceoverText(VOICEOVER_SEGMENTS[index + 1])
          : undefined,
        voice_settings: {
          stability,
          similarity_boost: similarity,
          style: 0,
          use_speaker_boost: true,
          speed,
        },
        seed: 27491,
      }),
    },
  )
  if (!response.ok) {
    throw new Error(
      `ElevenLabs ${response.status} for ${segment.key}: ${await response.text()}`,
    )
  }

  const payload = await response.json() as ElevenLabsTimingResponse
  const alignment = payload.alignment || payload.normalized_alignment
  if (!alignment || !payload.audio_base64) {
    throw new Error(`ElevenLabs returned no audio alignment for ${segment.key}.`)
  }

  const rawDuration = alignment.character_end_times_seconds.at(-1) || 0
  const availableDuration = segment.end - segment.start
  const tempo = Math.max(1, rawDuration / availableDuration)
  if (tempo > 1.18) {
    throw new Error(
      `${segment.key} is ${rawDuration.toFixed(2)}s but only ${availableDuration.toFixed(2)}s fit. `
      + 'Increase ELEVENLABS_SPEED slightly or shorten that segment.',
    )
  }

  const path = resolve(directory, `${String(index).padStart(2, '0')}-${segment.key}.mp3`)
  await writeFile(path, Buffer.from(payload.audio_base64, 'base64'))
  return {
    segment,
    path,
    rawDuration,
    tempo,
    captions: captionsFromAlignment(segment, alignment, tempo),
  }
}

async function stitchVoiceover(segments: GeneratedSegment[]) {
  const output = resolve(publicDirectory, 'voiceover.mp3')
  const inputArguments = segments.flatMap((segment) => ['-i', segment.path])
  const filters = segments.map((segment, index) => (
    `[${index}:a]atempo=${segment.tempo.toFixed(5)},`
    + `adelay=${Math.round(segment.segment.start * 1000)}:all=1[a${index}]`
  ))
  const inputs = segments.map((_, index) => `[a${index}]`).join('')
  const filter = [
    ...filters,
    `${inputs}amix=inputs=${segments.length}:duration=longest:normalize=0,`
      + `loudnorm=I=-16:TP=-1.5:LRA=11,apad,atrim=duration=${TOTAL_SECONDS}[out]`,
  ].join(';')

  await execute(ffmpeg, [
    '-y',
    ...inputArguments,
    '-filter_complex', filter,
    '-map', '[out]',
    '-c:a', 'libmp3lame',
    '-b:a', '192k',
    output,
  ])
  return output
}

await mkdir(publicDirectory, { recursive: true })
const temporaryDirectory = await mkdtemp(resolve(tmpdir(), 'komponist-voiceover-'))

try {
  const generated: GeneratedSegment[] = []
  for (const [index, segment] of VOICEOVER_SEGMENTS.entries()) {
    process.stdout.write(`Generating ${segment.key}… `)
    const result = await generateSegment(segment, index, temporaryDirectory)
    generated.push(result)
    console.log(
      `${result.rawDuration.toFixed(2)}s`
      + (result.tempo > 1 ? ` → fitted at ${result.tempo.toFixed(3)}x` : ''),
    )
  }

  const output = await stitchVoiceover(generated)
  const captions = generated.flatMap((segment) => segment.captions)
  await writeFile(
    resolve(here, 'voiceover-props.generated.json'),
    JSON.stringify({ voiceover: 'voiceover.mp3', captions }, null, 2),
  )
  await writeFile(
    resolve(publicDirectory, 'voiceover-alignment.json'),
    JSON.stringify({
      generated_at: new Date().toISOString(),
      voice_id: voiceId,
      model_id: modelId,
      speed,
      stability,
      similarity,
      segments: generated.map((segment) => ({
        key: segment.segment.key,
        start: segment.segment.start,
        end: segment.segment.end,
        raw_duration: segment.rawDuration,
        fitted_tempo: segment.tempo,
      })),
      captions,
    }, null, 2),
  )
  console.log(`Voice-over written to ${output}`)
  console.log('Render it with: npm run render:elevenlabs')
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true })
}
