<script setup>
import { computed } from 'vue'

const props = defineProps({
  cols: { type: Number, default: 24 },
  rows: { type: Number, default: 6 },
  // Fraction of cells that animate. Lower = sparser.
  density: { type: Number, default: 0.32 },
  // Fraction of animated cells that get the louder (filled-black) variant.
  loudness: { type: Number, default: 0.35 },
})

// Pre-randomize each cell once. Each component instance gets its own
// pattern so two adjacent fields never look in-phase.
const dots = computed(() => {
  const total = props.cols * props.rows
  const out = []
  for (let i = 0; i < total; i++) {
    const on = Math.random() < props.density
    out.push({
      on,
      // Stagger across a window so the field never pulses as a whole.
      d: (Math.random() * 2.6).toFixed(2),
      t: (1.4 + Math.random() * 1.6).toFixed(2),
      loud: on && Math.random() < props.loudness,
    })
  }
  return out
})
</script>

<template>
  <div
    class="dot-field"
    :style="{ '--cols': cols, '--rows': rows }"
    aria-hidden="true"
  >
    <span
      v-for="(d, i) in dots"
      :key="i"
      class="dot"
      :class="{ on: d.on, loud: d.loud }"
      :style="{ '--d': d.d + 's', '--t': d.t + 's' }"
    />
  </div>
</template>

<style scoped>
.dot-field {
  display: grid;
  grid-template-columns: repeat(var(--cols), 1fr);
  grid-template-rows: repeat(var(--rows), 1fr);
  width: 100%;
  height: 100%;
  gap: 0;
}
.dot {
  position: relative;
  width: 100%;
  height: 100%;
}
/* The visual is a single tiny square in the centre of the cell. The
   animation grows it and darkens it, so the pattern reads as moving "data". */
.dot::before {
  content: '';
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 1.5px;
  height: 1.5px;
  background: rgba(10, 10, 10, .14);
  border-radius: 50%;
}
.dot.on::before {
  animation: dot-pulse var(--t) ease-in-out var(--d) infinite;
}
.dot.on.loud::before {
  animation: dot-loud var(--t) ease-in-out var(--d) infinite;
}
@keyframes dot-pulse {
  0%, 100% { width: 1.5px; height: 1.5px; background: rgba(10,10,10,.14); border-radius: 50%; }
  50%      { width: 3px;   height: 3px;   background: rgba(10,10,10,.6);  border-radius: 1px; }
}
@keyframes dot-loud {
  0%, 100% { width: 1.5px; height: 1.5px; background: rgba(10,10,10,.18); border-radius: 50%; }
  50%      { width: 4px;   height: 4px;   background: #0A0A0A;            border-radius: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .dot.on::before, .dot.on.loud::before { animation: none; }
}
</style>
