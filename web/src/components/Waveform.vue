<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

/**
 * A reactive bar-waveform visualizer. Two modes:
 *   1. live: animated bars driven by `level` 0..1 (e.g. mic RMS or processing).
 *   2. static: decoded peaks from the `src` audio URL, with a playback cursor.
 */
const props = defineProps({
  src: { type: String, default: '' },     // audio URL — decoded for static mode
  level: { type: Number, default: 0 },    // 0..1 input for live mode
  live: { type: Boolean, default: false },// pulse with level even without src
  bars: { type: Number, default: 64 },
  height: { type: Number, default: 56 },
  playing: { type: Boolean, default: false },
  progress: { type: Number, default: 0 }, // 0..1
})

const peaks = ref([])
const livePeaks = ref([])
let raf = null

async function decodePeaks(url) {
  try {
    const res = await fetch(url)
    const buf = await res.arrayBuffer()
    const ctx = new (window.OfflineAudioContext || window.webkitOfflineAudioContext)(1, 44100, 44100)
    const audio = await ctx.decodeAudioData(buf.slice(0))
    const data = audio.getChannelData(0)
    const block = Math.max(1, Math.floor(data.length / props.bars))
    const out = new Array(props.bars)
    let max = 0
    for (let i = 0; i < props.bars; i++) {
      let s = 0
      const start = i * block
      const end = Math.min(data.length, start + block)
      for (let j = start; j < end; j++) {
        const v = Math.abs(data[j])
        if (v > s) s = v
      }
      out[i] = s
      if (s > max) max = s
    }
    if (max > 0) for (let i = 0; i < out.length; i++) out[i] /= max
    peaks.value = out
  } catch {
    peaks.value = []
  }
}

watch(() => props.src, (v) => { if (v) decodePeaks(v) }, { immediate: true })

function startLiveLoop() {
  // Roll the live level into a sliding window of bars for a flowing wave.
  const buf = new Array(props.bars).fill(0)
  const tick = () => {
    buf.shift()
    // Add some randomness so it looks alive even on a steady signal.
    const jitter = (Math.random() - 0.5) * 0.08
    buf.push(Math.max(0, Math.min(1, props.level + jitter)))
    livePeaks.value = [...buf]
    raf = requestAnimationFrame(tick)
  }
  tick()
}

onMounted(() => { if (props.live) startLiveLoop() })
onBeforeUnmount(() => { if (raf) cancelAnimationFrame(raf) })
watch(() => props.live, (v) => {
  if (v && !raf) startLiveLoop()
  if (!v && raf) { cancelAnimationFrame(raf); raf = null; livePeaks.value = [] }
})

const useLive = () => props.live && !props.src
</script>

<template>
  <div class="wf" :style="{ height: height + 'px' }">
    <div
      v-for="(p, i) in (useLive() ? livePeaks : peaks)"
      :key="i"
      class="bar"
      :class="{ played: !useLive() && (i / bars) <= progress }"
      :style="{ height: Math.max(8, p * 100) + '%' }"
    />
    <template v-if="!useLive() && peaks.length === 0">
      <div v-for="i in bars" :key="'p' + i" class="bar placeholder" :style="{ height: 18 + Math.sin(i / 3) * 8 + '%' }" />
    </template>
  </div>
</template>

<style scoped>
.wf {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1px;
  width: 100%;
  min-width: 0;
  padding: 6px 4px;
  border-radius: var(--r-md);
  background: var(--bg);
  border: 1px solid var(--border);
  overflow: hidden;
  box-sizing: border-box;
}
.bar {
  flex: 1 1 0;
  min-width: 1px;          /* allow the row to shrink under tight columns */
  background: var(--ink-4);
  border-radius: 1px;
  transition: height .12s var(--ease), background .15s var(--ease);
}
.bar.played { background: var(--accent); }
.bar.placeholder { background: var(--border-strong); opacity: .5; }
</style>
