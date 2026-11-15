<script setup>
import { ref, computed, onBeforeUnmount, watch } from 'vue'
import Waveform from './Waveform.vue'

const props = defineProps({
  src: { type: String, required: true },
  compact: { type: Boolean, default: false },
})

const audio = ref(null)
const playing = ref(false)
const progress = ref(0)
const duration = ref(0)

function ensureAudio() {
  if (audio.value) return audio.value
  const el = new Audio(props.src)
  el.preload = 'metadata'
  el.addEventListener('timeupdate', () => {
    progress.value = el.duration ? el.currentTime / el.duration : 0
  })
  el.addEventListener('loadedmetadata', () => { duration.value = el.duration || 0 })
  el.addEventListener('ended', () => { playing.value = false; progress.value = 0 })
  audio.value = el
  return el
}

function toggle() {
  const el = ensureAudio()
  if (playing.value) { el.pause(); playing.value = false }
  else { el.play(); playing.value = true }
}

function fmt(s) {
  if (!isFinite(s)) return '0:00'
  const m = Math.floor(s / 60)
  const r = Math.floor(s % 60)
  return `${m}:${r.toString().padStart(2, '0')}`
}

const elapsed = computed(() => fmt((audio.value?.currentTime) || 0))
const total = computed(() => fmt(duration.value))

watch(() => props.src, () => {
  if (audio.value) { audio.value.pause(); audio.value = null }
  playing.value = false; progress.value = 0; duration.value = 0
})

onBeforeUnmount(() => { if (audio.value) { audio.value.pause(); audio.value = null } })
</script>

<template>
  <div class="player" :class="{ compact }">
    <button class="play" @click="toggle" :aria-label="playing ? 'Pause' : 'Play'">
      <svg v-if="!playing" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
      <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>
    </button>
    <Waveform
      :src="src"
      :progress="progress"
      :playing="playing"
      :height="compact ? 38 : 52"
      :bars="compact ? 36 : 48"
      class="player-wave"
    />
    <div class="time">{{ elapsed }} <span>/ {{ total }}</span></div>
  </div>
</template>

<style scoped>
.player {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border-radius: var(--r-md);
  background: var(--surface);
  border: 1px solid var(--border);
  /* Critical: lets the player participate in a shrinking flex/grid context
     without overflowing the parent card. The waveform inside takes
     `flex: 1 1 0; min-width: 0` to absorb the slack. */
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  box-sizing: border-box;
}
.player-wave {
  flex: 1 1 0;
  min-width: 0;
}
.play {
  width: 34px; height: 34px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
  display: grid; place-items: center;
  padding: 0;
  box-shadow: 0 4px 12px -4px rgba(10, 10, 10, .35);
}
.play:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
.time {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-2);
  flex: 0 0 auto;
  min-width: 56px;
  text-align: right;
  letter-spacing: -0.02em;
  white-space: nowrap;
}
.time span { color: var(--ink-4); }
.player.compact { gap: 8px; padding: 6px; }
.player.compact .play { width: 28px; height: 28px; }
.player.compact .time { min-width: 48px; font-size: 11px; }
</style>
