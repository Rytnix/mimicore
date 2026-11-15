<script setup>
import { computed } from 'vue'

const props = defineProps({
  width:  { type: Number, default: 280 },
  height: { type: Number, default: 110 },
  /** Animation speed multiplier; >1 slows everything down. */
  speed:  { type: Number, default: 1 },
})

/* ------------------------------------------------------------------------
   Compose chaotic-but-musical paths: a carrier sine modulated by an
   amplitude envelope (also a sine) — gives "bunched peaks, quiet valleys"
   instead of a uniform wave.

   Seamless-loop math: the path is drawn over t ∈ [0, 1] mapping to x ∈
   [0, 2·W]. The animation translates by -W (one full visible width). For
   that translate to land back on itself, the function must satisfy
   `y(t + 0.5) === y(t)`. Working through it for the sin(2π·f·t + φ) terms,
   that requires `f` to be an *even integer* — anything else leaves a phase
   discontinuity at the seam, which is the "patched" jump you saw before.
   So every f1/f2 below is an even integer, and we encode variety via
   different *combinations* and phase offsets, not fractional frequencies.
------------------------------------------------------------------------ */
function buildPath({ yMid, amp, phase, f1, f2, w, samples = 240 }) {
  let d = ''
  for (let i = 0; i <= samples; i++) {
    const t = i / samples
    const x = t * w
    const env = 0.55 + 0.45 * Math.sin(t * f2 * Math.PI * 2 + phase * 0.7)
    const y = yMid + amp * env * Math.sin(t * f1 * Math.PI * 2 + phase)
    d += (i === 0 ? 'M ' : ' L ') + `${x.toFixed(1)} ${y.toFixed(1)}`
  }
  return d
}

/* Drawing area = 2× visible width so translateX(-W) lines up with one
   complete repeat. Combined with even-integer frequencies above, the loop
   is mathematically seamless. */
const drawW = computed(() => props.width * 2)
const cy = computed(() => props.height / 2)

function stack({ baseAmp, phase, f1, f2, count, dy, ampStep = 1.2 }) {
  const arr = []
  for (let i = 0; i < count; i++) {
    arr.push({
      d: buildPath({
        yMid: cy.value + (i - count / 2) * dy,
        amp:  baseAmp - i * ampStep,
        phase: phase + i * 0.06,
        f1, f2,
        w: drawW.value,
      }),
      i,
    })
  }
  return arr
}

// Layer 0 — yellow back-fill silhouette (wide, slow envelope)
const yellow = computed(() => buildPath({
  yMid: cy.value, amp: cy.value * 0.85, phase: 0.2,
  f1: 2, f2: 4, w: drawW.value,
}))

// Layer 1 — dotted purple trace, same low-frequency family with a phase
// offset so it weaves through the yellow rather than tracing it.
const purple = computed(() => buildPath({
  yMid: cy.value, amp: cy.value * 0.78, phase: 0.9,
  f1: 2, f2: 6, w: drawW.value,
}))

// Layer 2 — magenta/pink stack of ~11 outlines (the dense braid)
const pinkStack = computed(() => stack({
  baseAmp: cy.value * 0.7, phase: 0.4, f1: 4, f2: 6,
  count: 11, dy: 1.0, ampStep: 0.6,
}))

// Layer 3 — coral red stack (higher carrier → tighter peaks)
const redStack = computed(() => stack({
  baseAmp: cy.value * 0.62, phase: 0.7, f1: 4, f2: 8,
  count: 9, dy: 1.4, ampStep: 0.8,
}))

// Layer 4 — main blue outline (thicker, foremost)
const blueMain = computed(() => buildPath({
  yMid: cy.value, amp: cy.value * 0.66, phase: 0.0,
  f1: 2, f2: 6, w: drawW.value,
}))

// Bokeh and grit are placed across the *visible* width only — they don't
// scroll, they hover. Pre-randomised once per mount.
const bokeh = computed(() => {
  const arr = []
  for (let i = 0; i < 8; i++) {
    arr.push({
      cx: 10 + Math.random() * (props.width - 20),
      cy: cy.value + (Math.random() - 0.5) * props.height * 0.6,
      r:  2 + Math.random() * 4.5,
      d:  (Math.random() * 4).toFixed(2),
      t:  (4.5 + Math.random() * 3.5).toFixed(2),
    })
  }
  return arr
})
const grit = computed(() => {
  const arr = []
  for (let i = 0; i < 16; i++) {
    arr.push({
      cx: Math.random() * props.width,
      cy: cy.value + (Math.random() - 0.5) * props.height * 0.85,
      r:  0.7 + Math.random() * 1.3,
    })
  }
  return arr
})

// CSS keyframe shift = -width (one full repeat of the doubled-up paths).
const shiftPx = computed(() => `-${props.width}px`)
</script>

<template>
  <svg
    :viewBox="`0 0 ${width} ${height}`"
    :width="width" :height="height"
    class="wb"
    aria-hidden="true"
  >
    <defs>
      <!-- Soft side-fades so the wave appears to dissolve into the card
           edges rather than terminate abruptly. -->
      <linearGradient id="wb-fade" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%"  stop-color="#fff" stop-opacity="0" />
        <stop offset="14%" stop-color="#fff" stop-opacity="1" />
        <stop offset="86%" stop-color="#fff" stop-opacity="1" />
        <stop offset="100%" stop-color="#fff" stop-opacity="0" />
      </linearGradient>
      <mask id="wb-mask">
        <rect :x="0" :y="0" :width="width" :height="height" fill="url(#wb-fade)" />
      </mask>

      <!-- Bokeh inner glow — the white circles in the reference look like
           soft-focus light points, not flat dots. -->
      <radialGradient id="wb-bokeh" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0%"  stop-color="#fff" stop-opacity="0.95" />
        <stop offset="60%" stop-color="#fff" stop-opacity="0.5" />
        <stop offset="100%" stop-color="#fff" stop-opacity="0" />
      </radialGradient>
    </defs>

    <g :mask="`url(#wb-mask)`">
      <!-- Horizontal carrier line — sits inside the mask so its endpoints
           fade like everything else and there's no hard edge at the seam. -->
      <line :x1="0" :y1="cy" :x2="width" :y2="cy" stroke="#1F2A8E" stroke-width="1.5" stroke-linecap="round" />

      <!-- Yellow back layer — slowest scroll for a sense of depth. -->
      <g class="travel slow" :style="{ '--shift': shiftPx }">
        <path :d="yellow" stroke="#F2C232" stroke-width="1.5" fill="none" stroke-opacity=".55" />
        <path :d="yellow" stroke="#F2C232" stroke-width="6"   fill="none" stroke-opacity=".10" />
      </g>

      <!-- Pink/magenta stack — the dense braid. Drawn behind the red. -->
      <g class="travel mid" :style="{ '--shift': shiftPx }">
        <path
          v-for="p in pinkStack"
          :key="'p' + p.i"
          :d="p.d"
          stroke="#D63978"
          :stroke-width="0.55 + (p.i % 3) * 0.15"
          fill="none"
          :stroke-opacity="0.55 + (p.i % 4) * 0.08"
        />
      </g>

      <!-- Coral red stack — slightly higher frequency, faster scroll. -->
      <g class="travel fast" :style="{ '--shift': shiftPx }">
        <path
          v-for="p in redStack"
          :key="'r' + p.i"
          :d="p.d"
          stroke="#E55A4D"
          :stroke-width="0.5 + (p.i % 3) * 0.18"
          fill="none"
          :stroke-opacity="0.55 + (p.i % 3) * 0.12"
        />
      </g>

      <!-- Dotted purple trace — uses dasharray for the stippled look. -->
      <g class="travel medfast" :style="{ '--shift': shiftPx }">
        <path
          :d="purple"
          stroke="#5B3A8E"
          stroke-width="1.4"
          fill="none"
          stroke-dasharray="1.4 3"
          stroke-opacity=".75"
          stroke-linecap="round"
        />
      </g>

      <!-- Main blue outline — foremost, thicker, with a touch of glow. -->
      <g class="travel medslow" :style="{ '--shift': shiftPx }">
        <path :d="blueMain" stroke="#1B2A8C" stroke-width="2.4" fill="none" stroke-linecap="round" />
        <path :d="blueMain" stroke="#1B2A8C" stroke-width="6"   fill="none" stroke-opacity=".10" stroke-linecap="round" />
      </g>
    </g>

    <!-- Bokeh dots — drift gently in place, on top of the wave field. -->
    <g class="bokeh">
      <circle
        v-for="(b, i) in bokeh"
        :key="'b' + i"
        :cx="b.cx" :cy="b.cy" :r="b.r"
        fill="url(#wb-bokeh)"
        :style="{ '--d': b.d + 's', '--t': b.t + 's' }"
      />
    </g>

    <!-- Tiny black grit specks for texture. -->
    <g class="grit">
      <circle
        v-for="(g, i) in grit"
        :key="'g' + i"
        :cx="g.cx" :cy="g.cy" :r="g.r"
        fill="#0A0A0A"
        opacity=".65"
      />
    </g>
  </svg>
</template>

<style scoped>
.wb { display: block; overflow: visible; }

/* Each layer scrolls at a slightly different speed so the bundle reads as a
   parallax field — the eye picks up depth without explicit Z. The shift is
   exactly one period of the path (= the visible width), so the loop is
   seamless. */
.travel {
  animation-name: wb-travel;
  animation-iteration-count: infinite;
  animation-timing-function: linear;
}
.travel.slow      { animation-duration: 12s; }
.travel.medslow   { animation-duration: 9s;  }
.travel.mid       { animation-duration: 7.5s;}
.travel.medfast   { animation-duration: 6s;  }
.travel.fast      { animation-duration: 5s;  }

@keyframes wb-travel {
  from { transform: translateX(0); }
  to   { transform: translateX(var(--shift)); }
}

/* Bokeh — soft float + breathing opacity. */
.bokeh circle {
  filter: blur(0.4px);
  animation: wb-float var(--t, 6s) ease-in-out var(--d, 0s) infinite;
}
@keyframes wb-float {
  0%, 100% { transform: translateY(0);    opacity: .55; }
  50%      { transform: translateY(-7px); opacity: .95; }
}

@media (prefers-reduced-motion: reduce) {
  .travel, .bokeh circle { animation: none; }
}
</style>
