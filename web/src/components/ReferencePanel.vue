<script setup>
import { ref, computed } from 'vue'
import { useStudioStore } from '../stores/studio'
import { useMicRecorder } from '../composables/useMicRecorder'
import ReferenceCard from './ReferenceCard.vue'
import Waveform from './Waveform.vue'

const store = useStudioStore()
const fileInput = ref(null)
const dragOver = ref(false)
const uploading = ref(false)
const error = ref('')

const mic = useMicRecorder()
const showRecorder = ref(false)

async function pickFiles(files) {
  if (!files || files.length === 0) return
  error.value = ''
  uploading.value = true
  for (const f of files) {
    try { await store.uploadRef(f) }
    catch (e) { error.value = String(e.message || e) }
  }
  uploading.value = false
}

function onPick(e) { pickFiles(e.target.files); e.target.value = '' }
function onDrop(e) {
  e.preventDefault(); dragOver.value = false
  pickFiles(e.dataTransfer?.files)
}

async function startRec() {
  error.value = ''
  const ok = await mic.start({ language: store.targetLanguage })
  if (!ok) { error.value = mic.error.value || 'Could not start microphone.'; return }
  showRecorder.value = true
}
async function stopRec() {
  const blob = await mic.stop()
  showRecorder.value = false
  if (!blob) return
  const file = new File([blob], `recording-${Date.now()}.webm`, { type: blob.type })
  uploading.value = true
  try { await store.uploadRef(file) }
  catch (e) { error.value = String(e.message || e) }
  uploading.value = false
}
function cancelRec() { mic.stop().then(() => { showRecorder.value = false }) }
</script>

<template>
  <section class="panel card">
    <header class="head">
      <div class="head-text">
        <h2>References</h2>
        <p class="hint">10–30s of voice — auto-cleaned on upload.</p>
      </div>
      <span class="pill" v-if="store.refList.length">{{ store.refList.length }}</span>
    </header>

    <!-- Drop / pick zone -->
    <div
      class="dropzone"
      :class="{ over: dragOver, busy: uploading }"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop="onDrop"
      @click="!showRecorder && fileInput.click()"
    >
      <input ref="fileInput" type="file" accept="audio/*,.m4a,.wav,.mp3,.webm" hidden multiple @change="onPick" />
      <template v-if="!showRecorder">
        <div class="icon" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3v12"/><path d="m7 8 5-5 5 5"/><path d="M5 21h14"/>
          </svg>
        </div>
        <div class="dz-text">
          <strong>{{ dragOver ? 'Drop to upload' : 'Drag audio here' }}</strong>
          <span>or click to browse · m4a · wav · mp3 · webm</span>
        </div>
      </template>

      <!-- Live mic recorder -->
      <div v-else class="rec" @click.stop>
        <div class="rec-head">
          <span class="pill live"><span class="dot" /> recording</span>
          <span class="rec-time">{{ mic.elapsed.value.toFixed(1) }}s</span>
        </div>
        <Waveform live :level="mic.level.value" :height="48" />
        <div v-if="mic.partialTranscript.value || mic.finalTranscript.value" class="rec-asr">
          <span class="final">{{ mic.finalTranscript.value }}</span>
          <span class="interim">{{ mic.partialTranscript.value }}</span>
        </div>
        <div v-else-if="mic.supportsSpeech" class="rec-hint">listening…</div>
        <div v-else class="rec-hint">(browser ASR unavailable — server will transcribe after stop)</div>
        <div class="rec-actions">
          <button class="ghost" @click="cancelRec">Cancel</button>
          <button class="primary" @click="stopRec">Stop & save</button>
        </div>
      </div>
    </div>

    <div class="zone-actions" v-if="!showRecorder">
      <button class="ghost full" @click="startRec">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>
        </svg>
        Record from mic
      </button>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <div class="list">
      <ReferenceCard
        v-for="r in store.refList"
        :key="r.id"
        :ref-data="r"
        :selected="store.selectedRefId === r.id"
        @select="store.selectRef(r.id)"
        @delete="store.deleteRef(r.id)"
      />
      <div v-if="store.refList.length === 0" class="empty">
        <span>No references yet. Upload or record one to begin.</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: sticky;
  top: 80px;
  /* Fill the grid cell so the panel's footer aligns with the composer's. */
  height: 100%;
  max-height: calc(100vh - 100px);
  overflow: hidden;
}
.head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px;
}
.head h2 { font-size: 17px; }
.head-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.hint { color: var(--ink-3); margin: 0; font-size: 12.5px; }

.dropzone {
  border: 1.5px dashed var(--border-strong);
  background: var(--bg);
  border-radius: var(--r-lg);
  padding: 18px 14px;
  display: flex; flex-direction: column; gap: 8px; align-items: center;
  cursor: pointer;
  transition: all .2s var(--ease);
  text-align: center;
}
.dropzone:hover { border-color: var(--ink); background: var(--bg-alt); }
.dropzone.over  { border-color: var(--ink); background: var(--bg-alt); transform: scale(1.01); }
.dropzone.busy { opacity: .8; }
.dropzone .icon {
  width: 38px; height: 38px;
  border-radius: 10px;
  background: var(--ink);
  color: var(--accent-ink);
  border: 0;
  display: grid; place-items: center;
}
.dz-text strong { display: block; font-size: 13px; font-weight: 500; color: var(--ink); }
.dz-text span { font-size: 11.5px; color: var(--ink-3); }

.rec { width: 100%; display: flex; flex-direction: column; gap: 10px; cursor: default; }
.rec-head { display: flex; align-items: center; justify-content: space-between; }
.rec-time { font-family: var(--mono); font-size: 12.5px; color: var(--ink-2); }
.rec-asr {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--r-md);
  padding: 8px 10px;
  font-size: 12.5px;
  color: var(--ink);
  min-height: 36px;
  text-align: left;
  line-height: 1.5;
}
.rec-asr .final { color: var(--ink); }
.rec-asr .interim { color: var(--ink-3); font-style: italic; }
.rec-hint { font-size: 11.5px; color: var(--ink-3); }
.rec-actions { display: flex; gap: 8px; justify-content: flex-end; }

.zone-actions { display: flex; }
.full { width: 100%; display: flex; align-items: center; justify-content: center; gap: 6px; }

.error {
  background: var(--err-soft);
  color: #7F1D1D;
  padding: 8px 10px;
  border-radius: var(--r-md);
  font-size: 12.5px;
  border: 1px solid rgba(239, 68, 68, .35);
}

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  flex: 1;
  margin: 0 -4px;
  padding: 2px 4px;
}
.empty {
  text-align: center;
  font-size: 12.5px;
  color: var(--ink-3);
  padding: 14px;
  border: 1px dashed var(--border);
  border-radius: var(--r-md);
}

@media (max-width: 1024px) {
  .panel { position: static; max-height: none; }
}
</style>
