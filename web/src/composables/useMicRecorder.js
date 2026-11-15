import { ref, shallowRef, onBeforeUnmount } from 'vue'
import { toBcp47 } from './langUtils'

// Module-level singleton lock. The browser only hands the mic to one
// MediaRecorder at a time; if two panels both call start(), the second one
// silently steals the device while the first instance still *thinks* it's
// recording. We refuse the second start and surface a clear error instead.
let _activeRecorderId = null
let _nextRecorderId = 1

/**
 * In-browser mic recorder. Streams a live RMS level (`level`) for waveform
 * rendering and yields the final audio blob on stop.  Optionally drives a
 * Web Speech API recognizer for *truly* realtime in-browser ASR (Chrome).
 */
export function useMicRecorder() {
  const _instanceId = _nextRecorderId++
  const recording = ref(false)
  const elapsed = ref(0)
  const level = ref(0)
  const partialTranscript = ref('')
  const finalTranscript = ref('')
  const error = ref('')

  let media = null
  let recorder = null
  let chunks = []
  let stream = null
  let ctx = null
  let analyser = null
  let raf = null
  let started = 0
  let timer = null
  let recognition = null

  const supportsSpeech =
    typeof window !== 'undefined' &&
    (window.SpeechRecognition || window.webkitSpeechRecognition)

  async function start(opts = {}) {
    error.value = ''
    chunks = []
    finalTranscript.value = ''
    partialTranscript.value = ''
    const lang = opts.language || ''

    if (_activeRecorderId !== null && _activeRecorderId !== _instanceId) {
      error.value = 'Another recording is already in progress — stop it first.'
      return false
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      error.value = 'Microphone capture needs HTTPS or http://localhost — your context is insecure.'
      return false
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      // Specific DOMException names → actionable error messages.
      const name = (e && e.name) || ''
      if (name === 'NotAllowedError')         error.value = 'Microphone permission denied — allow it in your browser.'
      else if (name === 'NotFoundError')      error.value = 'No microphone detected on this device.'
      else if (name === 'NotReadableError')   error.value = 'Microphone is in use by another app.'
      else if (name === 'OverconstrainedError') error.value = 'Microphone constraints not satisfiable.'
      else if (name === 'SecurityError')      error.value = 'Microphone blocked by browser security policy.'
      else                                    error.value = e?.message || 'Could not access microphone.'
      return false
    }

    _activeRecorderId = _instanceId

    // Live waveform: AnalyserNode → time-domain RMS at ~60Hz.
    ctx = new (window.AudioContext || window.webkitAudioContext)()
    const src = ctx.createMediaStreamSource(stream)
    analyser = ctx.createAnalyser()
    analyser.fftSize = 1024
    src.connect(analyser)
    const buf = new Uint8Array(analyser.fftSize)
    const tick = () => {
      analyser.getByteTimeDomainData(buf)
      let sum = 0
      for (let i = 0; i < buf.length; i++) {
        const v = (buf[i] - 128) / 128
        sum += v * v
      }
      level.value = Math.sqrt(sum / buf.length)
      raf = requestAnimationFrame(tick)
    }
    tick()

    // MediaRecorder for the final blob (browser picks webm/opus by default).
    recorder = new MediaRecorder(stream)
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
    recorder.start(250)

    // Truly realtime: browser SpeechRecognition (Chrome/Edge). Safe to skip.
    if (supportsSpeech) {
      const Rec = window.SpeechRecognition || window.webkitSpeechRecognition
      recognition = new Rec()
      recognition.continuous = true
      recognition.interimResults = true
      // Browsers need a BCP 47 tag like "hi-IN" — bare ISO 639-1 codes are
      // rejected for many languages, which is why Hindi live ASR was silent.
      recognition.lang = toBcp47(lang)
      recognition.onresult = (ev) => {
        let interim = ''
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const r = ev.results[i]
          if (r.isFinal) finalTranscript.value += r[0].transcript
          else interim += r[0].transcript
        }
        partialTranscript.value = interim
      }
      recognition.onerror = () => { /* Chrome quirks; non-fatal */ }
      try { recognition.start() } catch (_) {}
    }

    started = performance.now()
    timer = setInterval(() => {
      elapsed.value = (performance.now() - started) / 1000
    }, 100)
    recording.value = true
    return true
  }

  function stop() {
    return new Promise((resolve) => {
      if (!recorder) return resolve(null)
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        cleanup()
        resolve(blob)
      }
      recorder.stop()
    })
  }

  function cleanup() {
    if (raf) cancelAnimationFrame(raf)
    if (timer) clearInterval(timer)
    if (recognition) { try { recognition.stop() } catch (_) {} }
    if (stream) stream.getTracks().forEach((t) => t.stop())
    if (ctx) { try { ctx.close() } catch (_) {} }
    raf = null; timer = null; recognition = null; stream = null; ctx = null
    recording.value = false
    level.value = 0
    if (_activeRecorderId === _instanceId) _activeRecorderId = null
  }

  onBeforeUnmount(() => { if (recording.value) cleanup() })

  return { recording, elapsed, level, partialTranscript, finalTranscript, error, supportsSpeech, start, stop }
}
