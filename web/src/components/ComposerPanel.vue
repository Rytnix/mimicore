<script setup>
import { ref, computed, watch } from 'vue'
import { useStudioStore } from '../stores/studio'
import AudioPlayer from './AudioPlayer.vue'
import DictateBar from './DictateBar.vue'
import LanguagePicker from './LanguagePicker.vue'
import WaveBloom from './WaveBloom.vue'
import { useTyped } from '../composables/useTyped'

const heroTitle = useTyped(['Speak anything, in your voice.'], { speed: 38, startDelay: 200 })
const heroLede  = useTyped(
  ['Upload a short reference, write your script, and synthesise it in your own voice. Long passages split into paragraphs automatically.'],
  { speed: 14, startDelay: 1500 },
)

const store = useStudioStore()

const text = ref('')
const steps = ref(32)
const speed = ref(1.0)
const perParagraph = ref(false)
const batchSize = ref(4)
// AI script generator mode — when on, the script textarea is replaced by a
// prompt input + Generate button. Output of the LM lands in `text`.
const aiMode = ref(false)
const aiPrompt = ref('')
const aiBusy = ref(false)
const aiError = ref('')
// Target language is shared store state — the reference panel and dictation
// also read it (so live ASR + post-record Whisper don't, e.g., guess Urdu
// for a Hindi recording).
const language = computed({
  get: () => store.targetLanguage,
  set: (v) => { store.targetLanguage = v || '' },
})
const submitting = ref(false)
const error = ref('')

const charCount = computed(() => text.value.length)
const wordCount = computed(() => text.value.trim() ? text.value.trim().split(/\s+/).length : 0)
const longText = computed(() => charCount.value > 1500)

// 0–100 % fill for the segmented sliders. Drives `--p` via inline style.
function segPct(v, min, max) { return ((v - min) / (max - min)) * 100 + '%' }
const stepsPct = computed(() => segPct(steps.value, 8, 48))
const speedPct = computed(() => segPct(speed.value, 0.6, 1.4))
const batchPct = computed(() => segPct(batchSize.value, 1, 8))
const ref_ = computed(() => store.selectedRef)
// Clone needs a reference uploaded — transcription is informational, not a gate.
const refUsable = computed(() => ref_.value && ref_.value.status !== 'error')

const presets = [
  { label: 'Greeting', text: "Hi — this is my voice, cloned from a short recording. Pretty wild, isn't it?" },
  { label: 'Demo', text: "Welcome to the demo. Today we'll walk through how voice cloning works end to end, from a short reference recording to a fully synthesised paragraph." },
  { label: 'News', text: "Markets opened lower this morning as investors weighed fresh inflation data and shifting expectations for central bank policy in the coming quarter." },
  { label: 'Story', text: "She paused at the door, listened for the sound she'd been dreading, and — hearing nothing — stepped quietly into the hall." },
]

function setPreset(p) { text.value = p.text }

async function submit() {
  error.value = ''
  if (!ref_.value) { error.value = 'Upload or pick a reference voice on the left.'; return }
  if (ref_.value.status === 'error') { error.value = 'Reference failed to load — try re-uploading.'; return }
  if (!text.value.trim()) { error.value = 'Enter some text to synthesise.'; return }
  submitting.value = true
  try {
    await store.createJob({
      ref_id: ref_.value.id,
      text: text.value,
      steps: steps.value,
      speed: speed.value,
      per_paragraph: perParagraph.value,
      batch_size: batchSize.value,
      language: language.value || null,
    })
  } catch (e) {
    error.value = String(e.message || e)
  } finally {
    submitting.value = false
  }
}

watch(longText, (v) => { if (v && !perParagraph.value) perParagraph.value = true })

async function generateFromPrompt() {
  aiError.value = ''
  if (!aiPrompt.value.trim()) { aiError.value = 'Type a prompt first.'; return }
  aiBusy.value = true
  try {
    const { text: gen } = await store.generateScript(aiPrompt.value.trim())
    if (gen && gen.trim()) {
      text.value = gen.trim()
      aiMode.value = false
    } else {
      aiError.value = 'Model returned no text — try a different prompt.'
    }
  } catch (e) {
    aiError.value = String(e.message || e)
  } finally {
    aiBusy.value = false
  }
}
</script>

<template>
  <section class="panel">
    <div class="hero card">
      <div class="hero-bg" aria-hidden="true" />
      <div class="hero-inner">
        <div class="kicker">
          <span class="pill"><span class="dot" /> Cloning Studio</span>
        </div>
        <h2 class="title">
          <span class="typed">{{ heroTitle.text.value }}</span><span class="cursor" :class="{ off: heroTitle.done.value && heroLede.done.value }" />
        </h2>
        <p class="lede typed-lede">
          {{ heroLede.text.value }}
        </p>
      </div>
      <div class="hero-decor" aria-hidden="true">
        <WaveBloom :width="280" :height="110" />
      </div>
    </div>

    <!-- Reference summary (hidden until a ref exists — empty hint moved to textarea) -->
    <div class="ref-summary card" v-if="ref_">
      <div class="rs-row">
        <div class="rs-info">
          <span class="rs-label">Reference voice</span>
          <span class="rs-name">{{ ref_.name }}</span>
        </div>
        <span class="pill" :class="{
          ok: ref_.status === 'ready',
          live: ref_.status === 'transcribing',
          warn: ref_.status === 'queued',
          err: ref_.status === 'error',
        }"><span class="dot" />{{ ref_.status }}</span>
      </div>
      <AudioPlayer compact :src="`/api/refs/${ref_.id}/audio`" />
      <details v-if="ref_.transcript || ref_.status === 'transcribing' || ref_.status === 'queued'" class="rs-transcript">
        <summary>Reference transcript</summary>
        <p v-if="ref_.transcript">{{ ref_.transcript }}</p>
        <p v-else class="rs-hint">
          {{ ref_.status === 'queued' ? 'Queued — transcript will appear here…' : 'Transcribing audio…' }}
        </p>
      </details>
    </div>

    <!-- Composer -->
    <div class="composer card">
      <div class="composer-head">
        <div class="head-title">
          <h3>Script</h3>
          <LanguagePicker v-model="language" />
        </div>
        <div class="head-actions">
          <DictateBar v-model="text" />
          <button
            type="button"
            class="ghost xs ai-btn"
            :class="{ on: aiMode }"
            @click="aiMode = !aiMode"
            :title="aiMode ? 'Back to manual script' : 'Generate a script with AI'"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>
              <circle cx="12" cy="12" r="3.5"/>
            </svg>
            {{ aiMode ? 'Cancel AI' : 'AI' }}
          </button>
          <span class="sep" aria-hidden="true" />
          <div class="presets">
            <button v-for="p in presets" :key="p.label" class="ghost xs" @click="setPreset(p)">{{ p.label }}</button>
          </div>
        </div>
      </div>

      <!-- AI prompt mode: replaces the script textarea with a prompt box. -->
      <div v-if="aiMode" class="ai-pane">
        <div class="ai-head">
          <span class="ai-kicker">AI script generator</span>
          <span class="ai-hint">Describe what you want — a tone, a topic, a length.</span>
        </div>
        <textarea
          v-model="aiPrompt"
          rows="3"
          placeholder="e.g. A 90-second product update for a launch email — confident, warm, ~120 words."
          @keydown.meta.enter="generateFromPrompt"
          @keydown.ctrl.enter="generateFromPrompt"
        />
        <div v-if="aiError" class="error-msg">{{ aiError }}</div>
        <div class="ai-actions">
          <span class="action-hint"><kbd>⌘</kbd><kbd>⏎</kbd> to generate</span>
          <button class="primary" :disabled="aiBusy || !aiPrompt.trim()" @click="generateFromPrompt">
            <span v-if="aiBusy" class="spin" aria-hidden="true" />
            <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 12l4 4L19 6"/>
            </svg>
            {{ aiBusy ? 'Generating…' : 'Generate script' }}
          </button>
        </div>
      </div>

      <textarea
        v-else
        v-model="text"
        rows="7"
        :placeholder="ref_
          ? 'Type or paste your script — or hit Dictate to speak it. ⌘⏎ to clone.'
          : 'Upload a reference voice on the left, then type or dictate your script.'"
        @keydown.meta.enter="submit"
        @keydown.ctrl.enter="submit"
      />

      <div class="composer-meta">
        <span class="meta-pill" :class="{ warn: longText }">
          {{ wordCount }} words · {{ charCount }} chars
          <em v-if="longText">long — splitting recommended</em>
        </span>
      </div>

      <div class="params">
        <label class="param">
          <span class="param-label">Diffusion steps</span>
          <span class="slider-wrap">
            <span class="seg" :style="{ '--p': stepsPct }">
              <input type="range" min="8" max="48" step="2" v-model.number="steps" />
            </span>
            <span class="param-val">{{ steps }}</span>
          </span>
          <span class="param-hint">Higher = better quality, slower</span>
        </label>

        <label class="param">
          <span class="param-label">Speed</span>
          <span class="slider-wrap">
            <span class="seg" :style="{ '--p': speedPct }">
              <input type="range" min="0.6" max="1.4" step="0.05" v-model.number="speed" />
            </span>
            <span class="param-val">{{ speed.toFixed(2) }}×</span>
          </span>
          <span class="param-hint">1.0 is natural pace</span>
        </label>

        <label class="toggle">
          <input type="checkbox" v-model="perParagraph" />
          <span class="toggle-track"><span class="toggle-thumb" /></span>
          <span class="toggle-label">
            <strong>Per-paragraph mode</strong>
            <em>Split on blank lines · auto-paced for long passages</em>
          </span>
        </label>

        <label v-if="perParagraph" class="param">
          <span class="param-label">Batch size</span>
          <span class="slider-wrap">
            <span class="seg" :style="{ '--p': batchPct }">
              <input type="range" min="1" max="8" step="1" v-model.number="batchSize" />
            </span>
            <span class="param-val">{{ batchSize }}</span>
          </span>
          <span class="param-hint">More = better GPU usage; lower if you OOM</span>
        </label>
      </div>

      <div v-if="error" class="error-msg">{{ error }}</div>

      <div class="actions">
        <span class="action-hint">
          <kbd>⌘</kbd><kbd>⏎</kbd> to clone
        </span>
        <button class="primary big" :disabled="submitting || !refUsable || !text.trim()" @click="submit">
          <svg v-if="!submitting" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 3l14 9-14 9V3z"/>
          </svg>
          <span v-else class="spin" aria-hidden="true" />
          {{ submitting ? 'Queueing…' : 'Clone voice' }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 12px; }

/* Hero */
.hero {
  position: relative;
  padding: 22px 24px;
  overflow: hidden;
  background: var(--surface);
  isolation: isolate;
}
.hero-bg {
  position: absolute; inset: 0;
  z-index: 0;
  background:
    radial-gradient(900px 220px at -10% 120%, rgba(10,10,10,.06) 0%, transparent 55%),
    radial-gradient(620px 240px at 110% -30%, rgba(10,10,10,.05) 0%, transparent 50%),
    linear-gradient(135deg, #FFFFFF 0%, #F8F5EE 60%, #EFE9DC 100%);
  pointer-events: none;
}
.hero-bg::after {
  /* Faint grid hairlines that match the body's editorial backdrop. */
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(10, 10, 10, .04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(10, 10, 10, .04) 1px, transparent 1px);
  background-size: 56px 56px;
  pointer-events: none;
}
.hero-inner {
  position: relative;
  z-index: 2;
  max-width: 70%;
  /* Reserve the height of the typed paragraph so the layout doesn't jitter
     while the text fills in. */
  min-height: 132px;
}
.kicker { margin-bottom: 10px; }
.title {
  font-size: 26px;
  line-height: 1.18;
  letter-spacing: -0.025em;
  font-weight: 700;
  display: inline;
  white-space: pre-wrap;
}
.title .typed { white-space: pre-wrap; }
.lede {
  color: var(--ink-2);
  margin: 8px 0 0;
  font-size: 13.5px;
  max-width: 56ch;
  white-space: pre-wrap;
  min-height: 3.2em;          /* same trick — keep height stable */
}

/* Blinking cursor riding the end of the title until both lines finish. */
.cursor {
  display: inline-block;
  width: 2px;
  height: 0.95em;
  background: var(--ink);
  margin-left: 2px;
  vertical-align: -0.12em;
  animation: cursor-blink 0.95s steps(2, end) infinite;
}
.cursor.off { display: none; }
@keyframes cursor-blink { 50% { opacity: 0; } }

.hero-decor {
  position: absolute;
  right: 14px;
  bottom: 12px;
  z-index: 1;
  width: 280px;
  height: 110px;
  pointer-events: none;
  /* Subtle breathing on the whole bloom — the reference image has that
     "alive" feel and a 5–6 % scale wobble sells it without distracting. */
  animation: hero-breathe 6.5s ease-in-out infinite;
  transform-origin: 70% 50%;
}
@keyframes hero-breathe {
  0%, 100% { transform: scale(1) translateY(0); }
  50%      { transform: scale(1.04) translateY(-2px); }
}
@media (max-width: 760px) {
  .hero-decor { display: none; }
}
@media (prefers-reduced-motion: reduce) { .hero-decor { animation: none; } }

/* Selected ref summary */
.ref-summary { padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.ref-summary.empty { padding: 14px; text-align: center; color: var(--ink-3); font-size: 12.5px; }
.rs-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.rs-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.rs-label {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-3);
  font-weight: 500;
}
.rs-name { font-weight: 500; font-size: 14px; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rs-transcript p {
  margin: 4px 0 0;
  font-family: var(--serif);
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.55;
  max-height: 72px;
  overflow-y: auto;
}
.rs-transcript p.rs-hint { color: var(--ink-3); font-style: italic; }

/* Composer */
.composer { padding: 16px 18px; display: flex; flex-direction: column; gap: 12px; }
.composer-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap;
}
.head-title { display: inline-flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.composer-head h3 { font-size: 15px; }
.head-actions {
  display: inline-flex; align-items: center; gap: 8px;
  flex-wrap: wrap;
}
.head-actions .sep {
  width: 1px; height: 16px;
  background: var(--border);
}
.presets { display: inline-flex; gap: 6px; flex-wrap: wrap; }

.composer textarea {
  font-family: var(--serif);
  font-size: 15.5px;
  line-height: 1.65;
  background: var(--bg);
  border: 1px solid var(--border);
  min-height: 160px;
  padding: 14px 16px;
}
.composer textarea:focus { background: var(--surface); }

/* AI prompt pane — sits in place of the script textarea. */
.ai-pane {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border-radius: var(--r-md);
  background: var(--bg);
  border: 1px solid var(--ink);
  position: relative;
}
.ai-head { display: flex; flex-direction: column; gap: 2px; }
.ai-kicker {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-weight: 700;
  color: var(--ink);
}
.ai-hint { font-size: 12px; color: var(--ink-3); }
.ai-pane textarea {
  background: var(--surface);
  border-color: var(--border);
  font-family: var(--sans);
  font-size: 13.5px;
  min-height: 80px;
}
.ai-actions {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px;
}
.ai-actions .primary {
  display: inline-flex; align-items: center; gap: 6px;
  border-radius: 999px;
  padding: 8px 16px;
}

/* "AI" toggle in the head row. Active state inverts to filled black. */
.ai-btn {
  display: inline-flex; align-items: center; gap: 5px;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 10px !important;
}
.ai-btn:hover { border-color: var(--ink); color: var(--ink); }
.ai-btn.on {
  background: var(--ink);
  color: var(--accent-ink);
  border-color: var(--ink);
}

/* Reference transcript collapses into a discreet expander now */
.rs-transcript {
  font-size: 12px;
  color: var(--ink-3);
}
.rs-transcript > summary {
  cursor: pointer;
  list-style: none;
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-3);
  font-weight: 500;
  user-select: none;
}
.rs-transcript > summary::-webkit-details-marker { display: none; }
.rs-transcript > summary::before {
  content: '▸';
  font-size: 9px;
  color: var(--ink-4);
  transition: transform .18s var(--ease);
}
.rs-transcript[open] > summary::before { transform: rotate(90deg); }

.composer-meta { display: flex; justify-content: flex-end; }
.meta-pill {
  font-size: 11.5px;
  color: var(--ink-3);
  font-family: var(--mono);
}
.meta-pill em { color: var(--warn); font-style: normal; margin-left: 6px; }
.meta-pill.warn { color: var(--warn); }

/* Params */
.params { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; }
.param { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.param-label { font-size: 12px; color: var(--ink-2); font-weight: 500; }
.slider-wrap { display: flex; align-items: center; gap: 12px; }
.slider-wrap .seg { flex: 1; min-width: 0; }
.param-val {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink);
  min-width: 44px;
  text-align: right;
}
.param-hint { font-size: 11px; color: var(--ink-4); }

.toggle {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 12px 14px;
  border-radius: var(--r-md);
  cursor: pointer;
}
.toggle input { display: none; }
.toggle-track {
  width: 34px; height: 20px;
  background: var(--border-strong);
  border-radius: 999px;
  position: relative;
  transition: background .15s var(--ease);
  flex: 0 0 auto;
}
.toggle-thumb {
  position: absolute; top: 2px; left: 2px;
  width: 16px; height: 16px;
  background: var(--surface);
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0,0,0,.15);
  transition: transform .18s var(--ease);
}
.toggle input:checked + .toggle-track { background: var(--accent); }
.toggle input:checked + .toggle-track .toggle-thumb { transform: translateX(14px); }
.toggle-label { display: flex; flex-direction: column; gap: 2px; }
.toggle-label strong { font-size: 13px; font-weight: 500; }
.toggle-label em { font-size: 11.5px; color: var(--ink-3); font-style: normal; }

/* Actions */
.actions {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--border-soft);
}
.action-hint {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--ink-3);
}
.action-hint kbd {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 18px;
  padding: 0 4px;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-2);
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom-width: 1.5px;
  border-radius: 4px;
}
button.big {
  padding: 11px 20px;
  font-size: 14px;
  display: inline-flex; gap: 8px; align-items: center;
}
.spin {
  width: 13px; height: 13px;
  border: 2px solid rgba(255,255,255,.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.error-msg {
  background: var(--err-soft);
  color: #7F1D1D;
  padding: 8px 10px;
  border-radius: var(--r-md);
  font-size: 12.5px;
  border: 1px solid #FCA5A5;
}

@media (max-width: 760px) {
  .params { grid-template-columns: 1fr; }
  .hero-inner { max-width: 100%; }
  .hero-decor { display: none; }
}
</style>
