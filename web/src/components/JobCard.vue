<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import AudioPlayer from './AudioPlayer.vue'
import DotField from './DotField.vue'

const props = defineProps({ job: { type: Object, required: true } })

const showLog = ref(false)
const logEl = ref(null)

// Always derive the audio URL from the job id. The WS "done" event used to
// set job.output_url, but that's missing after a page refresh — the server's
// GET /api/jobs returns the bare job dict. Computing here means the player
// works immediately on reload.
const audioUrl = computed(() =>
  props.job.status === 'ready' ? `/api/jobs/${props.job.id}/audio` : null,
)

const stages = ['queued', 'running', 'synthesising', 'ready']
const stageIdx = computed(() => {
  const s = props.job.stage || props.job.status
  if (props.job.status === 'failed') return -1
  if (props.job.status === 'ready') return 3
  if (s === 'synthesising' || s === 'finalising') return 2
  if (props.job.status === 'running' || s === 'loading') return 1
  return 0
})

const statusPill = computed(() => {
  const s = props.job.status
  if (s === 'ready')   return { cls: 'ok',   label: 'ready' }
  if (s === 'failed')  return { cls: 'err',  label: 'failed' }
  if (s === 'running') return { cls: 'live', label: props.job.stage || 'running' }
  // queued: show position if we have one.
  const pos = props.job.queue_position
  return { cls: 'warn', label: pos > 1 ? `queued · #${pos}` : 'queued' }
})

const waitDetail = computed(() => {
  if (props.job.status !== 'queued') return null
  const r = props.job.wait_reason
  if (r) return r
  const pos = props.job.queue_position
  if (pos > 1) return `${pos - 1} job${pos > 2 ? 's' : ''} ahead`
  return 'starting…'
})

const eta = computed(() => {
  if (props.job.status !== 'running' || !props.job.started_at) return null
  const started = new Date(props.job.started_at).getTime()
  const elapsed = (Date.now() - started) / 1000
  return elapsed
})
const elapsedTick = ref(0)
setInterval(() => elapsedTick.value++, 1000)
const elapsedFmt = computed(() => {
  // eslint-disable-next-line no-unused-expressions
  elapsedTick.value
  if (!props.job.started_at) return '—'
  const started = new Date(props.job.started_at).getTime()
  const end = props.job.finished_at ? new Date(props.job.finished_at).getTime() : Date.now()
  const s = (end - started) / 1000
  return `${s.toFixed(1)}s`
})

const lastLog = computed(() => {
  const log = props.job.log || []
  for (let i = log.length - 1; i >= 0; i--) {
    if (log[i].trim()) return log[i]
  }
  return ''
})

watch(() => (props.job.log || []).length, async () => {
  if (!showLog.value) return
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
})

const textPreview = computed(() => {
  const t = props.job.text || ''
  return t.length > 220 ? t.slice(0, 220).trim() + '…' : t
})
</script>

<template>
  <article class="job" :class="['s-' + job.status]">
    <header class="row">
      <div class="who">
        <span class="ref-name" :title="job.ref_name">{{ job.ref_name }}</span>
        <span class="meta">
          {{ job.steps }} steps · {{ Number(job.speed).toFixed(2) }}× ·
          <span v-if="job.per_paragraph">paragraph</span><span v-else>single</span>
        </span>
      </div>
      <span class="pill" :class="statusPill.cls">
        <span class="dot" /> {{ statusPill.label }}
      </span>
    </header>

    <p class="quote">{{ textPreview }}</p>

    <!-- Stage track -->
    <div class="stages" :class="{ failed: job.status === 'failed' }">
      <div
        v-for="(s, i) in stages.slice(0, 3)"
        :key="s"
        class="stage"
        :class="{
          done: stageIdx > i || job.status === 'ready',
          active: stageIdx === i && job.status !== 'ready' && job.status !== 'failed',
        }"
      >
        <span class="dot" />
        <span class="lbl">{{ s }}</span>
      </div>
      <div class="stage" :class="{ done: job.status === 'ready', failed: job.status === 'failed' }">
        <span class="dot" />
        <span class="lbl">{{ job.status === 'failed' ? 'failed' : 'ready' }}</span>
      </div>
    </div>

    <!-- Dot-field processing animation while running/queued -->
    <div class="proc" v-if="job.status === 'running' || job.status === 'queued'">
      <div class="proc-dots"><DotField :cols="56" :rows="5" :density="0.36" :loudness="0.32" /></div>
      <span class="bar-meta">{{ elapsedFmt }}</span>
    </div>

    <!-- Wait reason (shown while queued by the scheduler) -->
    <div v-if="waitDetail" class="wait-detail">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>
      </svg>
      <span>{{ waitDetail }}</span>
    </div>

    <!-- Output -->
    <div v-if="audioUrl" class="output">
      <AudioPlayer :src="audioUrl" compact />
      <a class="dl" :href="audioUrl" :download="`clone-${job.id}.wav`">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14"/>
        </svg>
        Download
      </a>
    </div>

    <!-- Live log line -->
    <div v-if="(job.status === 'running' || job.status === 'queued') && lastLog" class="last-log" @click="showLog = !showLog" :title="'Click to ' + (showLog ? 'hide' : 'expand') + ' full log'">
      <span class="caret">▸</span>
      <code>{{ lastLog }}</code>
    </div>

    <div v-if="showLog && (job.log || []).length" ref="logEl" class="log">
      <pre><span v-for="(l, i) in job.log" :key="i">{{ l }}
</span></pre>
    </div>

    <footer class="row toolbar">
      <button v-if="(job.log || []).length" class="ghost xs" @click="showLog = !showLog">
        {{ showLog ? 'Hide log' : `Show log (${job.log.length})` }}
      </button>
      <span style="flex:1" />
      <span class="time" v-if="job.duration">{{ job.duration.toFixed(1) }}s output</span>
    </footer>
  </article>
</template>

<style scoped>
.job {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  animation: fade-up .35s var(--ease) both;
  position: relative;
  box-shadow: var(--shadow-1);
}
.job.s-running {
  border-color: var(--ink);
  box-shadow: 0 0 0 3px rgba(10, 10, 10, .06), var(--shadow-1);
}
.job.s-ready  { border-color: rgba(34, 197, 94, .35); }
.job.s-failed { border-color: rgba(239, 68, 68, .35); }

.row { display: flex; align-items: center; gap: 8px; }
.who { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ref-name { font-size: 13px; font-weight: 500; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.meta { font-family: var(--mono); font-size: 11px; color: var(--ink-3); }

.quote {
  margin: 0;
  font-family: var(--serif);
  font-size: 13px;
  color: var(--ink-2);
  line-height: 1.55;
  background: rgba(255, 255, 255, 0.4);
  border: 1px solid rgba(40, 16, 80, 0.06);
  border-radius: var(--r-md);
  padding: 8px 10px;
  max-height: 84px;
  overflow: hidden;
  position: relative;
}

.stages {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  padding: 4px 0;
}
.stage {
  display: flex; align-items: center; gap: 6px;
  font-size: 10.5px;
  color: var(--ink-4);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.stage .dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--border-strong);
  flex: 0 0 auto;
}
.stage.done   { color: var(--ok); }
.stage.done .dot { background: var(--ok); }
.stage.active { color: var(--accent); }
.stage.active .dot {
  background: var(--accent);
  box-shadow: 0 0 0 0 rgba(5,150,105,.5);
  animation: live-pulse 1.4s var(--ease) infinite;
}
.stage.failed { color: var(--err); }
.stage.failed .dot { background: var(--err); }

.proc { display: flex; align-items: center; gap: 10px; }
.proc-dots {
  flex: 1;
  height: 28px;
  border-radius: 6px;
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 4px 6px;
  overflow: hidden;
}
.bar-meta { font-family: var(--mono); font-size: 11px; color: var(--ink-3); min-width: 48px; text-align: right; }

.wait-detail {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11.5px;
  color: var(--ink-3);
  background: rgba(255, 255, 255, 0.4);
  border: 1px solid rgba(40, 16, 80, 0.06);
  border-radius: var(--r-md);
  padding: 5px 8px;
  align-self: flex-start;
}
.wait-detail svg { color: var(--accent); }

.output { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.dl {
  align-self: flex-end;
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11.5px;
  color: var(--ink-3);
  text-decoration: none;
  padding: 4px 8px;
  border-radius: var(--r-md);
}
.dl:hover { background: var(--bg-alt); color: var(--ink); }

.last-log {
  display: flex; gap: 8px; align-items: center;
  cursor: pointer;
  padding: 6px 8px;
  background: rgba(255, 255, 255, 0.4);
  border: 1px solid rgba(40, 16, 80, 0.06);
  border-radius: var(--r-md);
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-2);
  overflow: hidden;
}
.last-log code { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }
.last-log .caret { color: var(--ink-4); }

.log {
  background: #1A0F2E;
  color: #E1D8F2;
  border-radius: var(--r-md);
  padding: 10px 12px;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.55;
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid #2D1B4D;
}
.log pre { margin: 0; white-space: pre-wrap; word-break: break-word; }

.toolbar .xs { padding: 4px 8px; font-size: 11.5px; }
.time { font-family: var(--mono); font-size: 11px; color: var(--ink-3); }
</style>
