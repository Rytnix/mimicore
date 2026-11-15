<script setup>
import { ref, computed } from 'vue'
import { useStudioStore } from '../stores/studio'
import { useMicRecorder } from '../composables/useMicRecorder'
import Waveform from './Waveform.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const store = useStudioStore()
const mic = useMicRecorder()
const open = ref(false)
const transcribing = ref(false)
const error = ref('')

const liveText = computed(() => {
  // SpeechRecognition (Chrome/Edge) gives a free preview while we record.
  return (mic.finalTranscript.value + ' ' + mic.partialTranscript.value).trim()
})

async function startDictate() {
  error.value = ''
  const ok = await mic.start({ language: store.targetLanguage })
  if (!ok) { error.value = mic.error.value || 'Could not start microphone.'; return }
  open.value = true
}

async function finishDictate() {
  let blob
  try { blob = await mic.stop() }
  catch (e) { error.value = String(e.message || e); open.value = false; return }
  if (!blob) { open.value = false; return }
  transcribing.value = true
  try {
    const { text } = await store.transcribeBlob(
      blob, `dictation-${Date.now()}.webm`,
    )
    if (text && text.trim()) {
      const cur = (props.modelValue || '').trim()
      const sep = cur ? (cur.endsWith('.') || cur.endsWith('?') || cur.endsWith('!') ? ' ' : ' ') : ''
      emit('update:modelValue', cur ? cur + sep + text.trim() : text.trim())
    } else {
      error.value = 'No speech detected — try again a little louder.'
    }
  } catch (e) {
    error.value = String(e.message || e)
  } finally {
    transcribing.value = false
    open.value = false
  }
}

async function cancelDictate() {
  try { await mic.stop() } catch (_) {}
  open.value = false
  error.value = ''
}
</script>

<template>
  <div class="dictate">
    <button
      v-if="!open && !transcribing"
      class="ghost xs trigger"
      type="button"
      @click="startDictate"
      title="Speak your script — Whisper will transcribe and drop it in"
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <rect x="9" y="3" width="6" height="12" rx="3"/>
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>
      </svg>
      Dictate
    </button>

    <button v-else-if="transcribing" class="ghost xs busy" type="button" disabled>
      <span class="spin" />
      Transcribing…
    </button>

    <div v-else class="rec-bar" role="dialog" aria-label="Dictation in progress">
      <div class="rec-meta">
        <span class="pill live"><span class="dot" /> recording</span>
        <span class="rec-time">{{ mic.elapsed.value.toFixed(1) }}s</span>
      </div>
      <div class="wave-wrap">
        <Waveform live :level="mic.level.value" :height="32" />
      </div>
      <div v-if="liveText" class="preview">{{ liveText }}</div>
      <div v-else class="preview hint">Speak your script — Whisper will fill it in.</div>
      <div class="rec-actions">
        <button class="ghost xs" type="button" @click="cancelDictate">Cancel</button>
        <button class="primary xs" type="button" @click="finishDictate">Stop &amp; transcribe</button>
      </div>
    </div>

    <div v-if="error" class="err">{{ error }}</div>
  </div>
</template>

<style scoped>
.dictate { display: contents; }

.trigger { display: inline-flex; align-items: center; gap: 5px; }

.busy {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--ink-3); cursor: progress;
}
.spin {
  width: 11px; height: 11px;
  border: 2px solid rgba(124, 58, 237, .25);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.rec-bar {
  grid-column: 1 / -1;
  width: 100%;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  background: linear-gradient(180deg, var(--accent-soft) 0%, rgba(255,255,255,.7) 100%);
  border: 1px solid rgba(124, 58, 237, .35);
  border-radius: var(--r-md);
  animation: fade-in .2s var(--ease) both;
}
.rec-meta { display: flex; align-items: center; gap: 8px; }
.rec-time { font-family: var(--mono); font-size: 11.5px; color: var(--ink-2); min-width: 40px; }
.wave-wrap { min-width: 0; }
.preview {
  grid-column: 1 / -1;
  font-size: 12.5px;
  color: var(--ink);
  line-height: 1.45;
  font-family: var(--serif);
  max-height: 56px; overflow-y: auto;
}
.preview.hint { color: var(--ink-3); font-style: italic; font-family: var(--sans); font-size: 11.5px; }
.rec-actions { grid-column: 1 / -1; display: flex; gap: 6px; justify-content: flex-end; }

.err {
  grid-column: 1 / -1;
  margin-top: 4px;
  background: var(--err-soft);
  border: 1px solid rgba(239, 68, 68, .35);
  color: #7F1D1D;
  padding: 6px 10px;
  border-radius: var(--r-md);
  font-size: 11.5px;
}

@keyframes fade-in { from { opacity: 0; transform: translateY(-2px); } to { opacity: 1; transform: none; } }
</style>
