<script setup>
import { computed, ref } from 'vue'
import AudioPlayer from './AudioPlayer.vue'
import DotField from './DotField.vue'

const props = defineProps({
  refData: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'delete'])

const expanded = ref(false)
const showRaw = ref(false)

const status = computed(() => props.refData.status || 'queued')
const cleaned = computed(() => Boolean(props.refData.cleaned))
const audioSrc = computed(() => {
  const base = `/api/refs/${props.refData.id}/audio`
  return showRaw.value ? `${base}?raw=1` : base
})
const transcript = computed(() => {
  const segs = props.refData.liveSegments || props.refData.segments || []
  if (segs.length) return segs.map((s) => s.text).join(' ').trim()
  return props.refData.transcript || ''
})

function fmtDur(s) {
  if (!s) return '—'
  return `${s.toFixed(1)}s`
}
</script>

<template>
  <article
    class="ref"
    :class="{ selected, [status]: true }"
    @click="emit('select')"
    tabindex="0"
  >
    <div class="row top">
      <div class="title">
        <span class="name" :title="refData.name">{{ refData.name }}</span>
        <span class="meta">
          {{ fmtDur(refData.duration) }}<span v-if="refData.language"> · {{ refData.language }}</span>
        </span>
      </div>
      <span class="pill" :class="{
        ok: status === 'ready',
        live: status === 'transcribing',
        warn: status === 'queued',
        err: status === 'error',
      }">
        <span class="dot" />
        {{ status === 'ready' ? 'ready' : status }}
      </span>
    </div>

    <div v-if="cleaned" class="badge-row">
      <span class="badge" title="Auto-cleaned: noise reduction, silence trimming, loudness normalisation">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="9"/>
        </svg>
        Studio-cleaned
      </span>
    </div>

    <div v-if="status === 'ready' && expanded" class="player-wrap" @click.stop>
      <AudioPlayer compact :src="audioSrc" />
      <div v-if="cleaned" class="ab-toggle">
        <button class="ghost xs" :class="{ active: !showRaw }" @click="showRaw = false">Cleaned</button>
        <button class="ghost xs" :class="{ active: showRaw }" @click="showRaw = true">Raw</button>
      </div>
    </div>

    <div class="transcript">
      <template v-if="transcript">
        <span class="t-text" :class="{ live: status === 'transcribing' }">{{ transcript }}</span>
      </template>
      <template v-else-if="status === 'transcribing'">
        <div class="proc-row">
          <div class="proc-box"><DotField :cols="32" :rows="5" :density="0.40" :loudness="0.36" /></div>
          <span class="proc-label">transcribing audio…</span>
        </div>
      </template>
      <template v-else-if="status === 'queued'">
        <div class="proc-row">
          <div class="proc-box"><DotField :cols="32" :rows="5" :density="0.20" :loudness="0.15" /></div>
          <span class="proc-label">queued for transcription…</span>
        </div>
      </template>
      <template v-else-if="status === 'error'">
        <span class="err-text">{{ refData.error || 'transcription failed' }}</span>
      </template>
      <template v-else>
        <span class="placeholder">no transcript yet</span>
      </template>
    </div>

    <div class="row actions" @click.stop>
      <button class="ghost xs" @click="expanded = !expanded" v-if="status === 'ready'">
        {{ expanded ? 'Hide audio' : 'Play' }}
      </button>
      <span style="flex:1" />
      <button class="ghost xs danger" @click="emit('delete')" title="Delete">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
        </svg>
      </button>
    </div>
  </article>
</template>

<style scoped>
.ref {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: pointer;
  transition: all .2s var(--ease);
  outline: none;
  position: relative;
  animation: fade-up .35s var(--ease) both;
}
.ref:hover { border-color: var(--border-strong); transform: translateY(-1px); box-shadow: var(--shadow-2); }
.ref.selected {
  border-color: var(--ink);
  box-shadow: 0 0 0 3px rgba(10, 10, 10, .08), var(--shadow-2);
  background: var(--surface);
}
.ref.transcribing { border-color: rgba(10, 10, 10, 0.18); }
.ref.error        { border-color: rgba(239, 68, 68, .35); }

.row { display: flex; align-items: center; gap: 8px; }
.row.top { justify-content: space-between; }
.title { display: flex; flex-direction: column; min-width: 0; gap: 2px; }
.name {
  font-weight: 500; font-size: 13.5px; color: var(--ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 220px;
}
.meta { font-size: 11px; color: var(--ink-3); font-family: var(--mono); letter-spacing: -0.01em; }

.transcript {
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.55;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: 8px 10px;
  max-height: 92px;
  overflow-y: auto;
  font-family: var(--serif);
}
.proc-row {
  display: flex; align-items: center; gap: 10px;
  font-family: var(--sans);
}
.proc-box {
  flex: 0 0 130px;
  height: 36px;
  border-radius: 4px;
  overflow: hidden;
}
.proc-label {
  font-size: 11.5px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
}
.placeholder {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--ink-3);
  font-style: italic;
  font-family: var(--sans);
  font-size: 12px;
}
.placeholder.shimmer { background-clip: padding-box; }
.err-text { color: #7F1D1D; font-family: var(--sans); }
.t-text.live::after {
  content: '▍';
  display: inline-block;
  margin-left: 2px;
  color: var(--accent);
  animation: blink 1s steps(2) infinite;
}
@keyframes blink { 50% { opacity: 0; } }

.player-wrap { padding-top: 2px; display: flex; flex-direction: column; gap: 6px; }

.badge-row { display: flex; gap: 6px; flex-wrap: wrap; }
.badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 8px;
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.01em;
  color: var(--ok);
  background: var(--ok-soft);
  border: 1px solid rgba(34, 197, 94, .3);
  border-radius: 999px;
}
.badge svg { color: var(--ok); }

.ab-toggle {
  display: inline-flex;
  gap: 0;
  padding: 2px;
  background: var(--bg-alt);
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  align-self: flex-end;
}
.ab-toggle .xs { padding: 2px 10px; font-size: 10.5px; border: none; background: transparent; color: var(--ink-3); }
.ab-toggle .xs.active { background: var(--surface); color: var(--ink); box-shadow: var(--shadow-1); }

.actions { gap: 6px; }
.xs { padding: 4px 9px; font-size: 11.5px; }
.danger { color: var(--ink-4); }
.danger:hover { color: var(--err); background: var(--err-soft); }
</style>
