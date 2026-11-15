<script setup>
import { computed } from 'vue'

const props = defineProps({
  width:  { type: Number, default: 240 },
  height: { type: Number, default: 96 },
  /** Number of integer periods drawn across one viewBox width. The path is
   *  rendered over 2×viewBox so a -100% translation loops seamlessly. */
  periods: { type: Number, default: 2 },
  ticks:  { type: Number, default: 80 },
  rungs:  { type: Number, default: 26 },
})

// Drawing area is twice the viewBox so a translateX(-50%) loops back onto
// itself — the second half exactly repeats the first.
const drawW = computed(() => props.width * 2)
const periodPx = computed(() => props.width / props.periods)
const amp = computed(() => props.height * 0.34)

function sample(arr, phaseOffset) {
  const out = []
  const N = props.ticks
  for (let i = 0; i <= N; i++) {
    const x = (i / N) * drawW.value
    const phase = (x / periodPx.value) * Math.PI * 2 + phaseOffset
    const y = props.height / 2 + Math.sin(phase) * amp.value
    out.push([x, y])
  }
  return out
}

const strandA = computed(() => sample(null, 0))
const strandB = computed(() => sample(null, Math.PI))

function asPath(pts) {
  return 'M ' + pts.map(p => `${p[0].toFixed(2)} ${p[1].toFixed(2)}`).join(' L ')
}

// Rungs sampled at integer fractions across the drawing area. `depth` is
// the relative span between strands (0 = strands cross, 1 = max apart);
// we use it to fade rungs nearest the crossings — that single trick reads
// as 3D rotation more than any actual 3D math would.
const rungLines = computed(() => {
  const out = []
  for (let i = 0; i < props.rungs * 2; i++) {
    const t = (i + 0.5) / (props.rungs * 2)
    const x = t * drawW.value
    const phase = (x / periodPx.value) * Math.PI * 2
    const yA = props.height / 2 + Math.sin(phase) * amp.value
    const yB = props.height / 2 + Math.sin(phase + Math.PI) * amp.value
    const span = Math.abs(yA - yB) / (2 * amp.value)
    out.push({ x, yA, yB, depth: span })
  }
  return out
})
</script>

<template>
  <svg
    :viewBox="`0 0 ${width} ${height}`"
    :width="width"
    :height="height"
    class="dna"
    aria-hidden="true"
  >
    <defs>
      <linearGradient id="mc-strand-a" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%"   stop-color="#0A0A0A" stop-opacity="0" />
        <stop offset="20%"  stop-color="#0A0A0A" stop-opacity=".75" />
        <stop offset="80%"  stop-color="#0A0A0A" stop-opacity=".75" />
        <stop offset="100%" stop-color="#0A0A0A" stop-opacity="0" />
      </linearGradient>
      <linearGradient id="mc-strand-b" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%"   stop-color="#6B7280" stop-opacity="0" />
        <stop offset="20%"  stop-color="#6B7280" stop-opacity=".55" />
        <stop offset="80%"  stop-color="#6B7280" stop-opacity=".55" />
        <stop offset="100%" stop-color="#6B7280" stop-opacity="0" />
      </linearGradient>
      <linearGradient id="mc-fade" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%"   stop-color="#fff" stop-opacity="0" />
        <stop offset="15%"  stop-color="#fff" stop-opacity="1" />
        <stop offset="85%"  stop-color="#fff" stop-opacity="1" />
        <stop offset="100%" stop-color="#fff" stop-opacity="0" />
      </linearGradient>
      <mask id="mc-mask">
        <rect :x="0" :y="0" :width="width" :height="height" fill="url(#mc-fade)" />
      </mask>
    </defs>

    <g :mask="`url(#mc-mask)`">
      <g class="travel">
        <!-- Rungs first so strands paint on top of the connectors. -->
        <g class="rungs">
          <line
            v-for="(r, i) in rungLines"
            :key="'r' + i"
            :x1="r.x" :y1="r.yA"
            :x2="r.x" :y2="r.yB"
            :stroke="`rgba(10,10,10,${(0.16 + r.depth * 0.45).toFixed(3)})`"
            stroke-width="1.3"
            stroke-linecap="round"
          />
        </g>
        <path :d="asPath(strandA)" stroke="url(#mc-strand-a)" stroke-width="2" fill="none" stroke-linecap="round" />
        <path :d="asPath(strandB)" stroke="url(#mc-strand-b)" stroke-width="2" fill="none" stroke-linecap="round" />
      </g>
    </g>
  </svg>
</template>

<style scoped>
.dna { display: block; overflow: visible; }
.travel {
  animation: dna-revolve 4.5s linear infinite;
  transform-origin: 0 0;
}
/* Translate by -viewBox width — equivalent to -50 % of the drawing width,
   which is exactly one repeat. After one cycle the path looks identical
   to the start, so the loop is seamless. */
@keyframes dna-revolve {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }
}
@media (prefers-reduced-motion: reduce) { .travel { animation: none; } }
</style>
