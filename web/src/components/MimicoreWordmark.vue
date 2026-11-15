<script setup>
const props = defineProps({
  /** Font-size in px. The wave amplitude scales from this. */
  size: { type: Number, default: 18 },
  /** Bold weight tier — 700 for headers, 800 for hero/centre, 600 for hints. */
  weight: { type: Number, default: 800 },
})
const chars = 'Mimicore'.split('')
</script>

<template>
  <span
    class="wm"
    :style="{
      '--wm-size': size + 'px',
      '--wm-weight': weight,
      '--wm-amp': Math.max(2, size * 0.18) + 'px',
    }"
    aria-label="Mimicore"
  >
    <!-- Per-letter wave + a single travelling highlight dot under the line.
         The wave is what gives "Mimicore" its identity — a Mexican-wave
         ripple that loops through the letters every few seconds. -->
    <span
      v-for="(c, i) in chars"
      :key="i"
      class="ch"
      :style="{ '--i': i, '--n': chars.length }"
      aria-hidden="true"
    >{{ c }}</span>
    <span class="sweep" aria-hidden="true" />
  </span>
</template>

<style scoped>
.wm {
  position: relative;
  display: inline-flex;
  align-items: baseline;
  font-family: var(--sans);
  font-weight: var(--wm-weight, 800);
  font-size: var(--wm-size, 18px);
  letter-spacing: -0.02em;
  line-height: 1;
  color: currentColor;
  /* tighten descender so .sweep underline aligns crisply */
  padding-bottom: calc(var(--wm-amp) * 0.6);
}

/* ---------- per-letter wave ---------- */
/*
  Each letter runs the same keyframe but with a delay tied to its position.
  The total wave period (5s) is divided across N letters so the bump
  travels left → right cleanly and resets seamlessly. Cubic ease keeps the
  motion buttery — no perceptible "thunk".
*/
.ch {
  display: inline-block;
  transform-origin: 50% 100%;
  animation: wm-ripple 5s cubic-bezier(.4, 0, .2, 1) infinite;
  animation-delay: calc(var(--i) * 5s / var(--n) * 0.5);
  will-change: transform, color;
}
@keyframes wm-ripple {
  /* Most of the cycle the letter sits at rest. Around the wave's pass
     (10 → 18 % of the loop) it lifts and gets a brief accent colour. */
  0%, 8%, 22%, 100% {
    transform: translateY(0);
    color: currentColor;
  }
  14% {
    transform: translateY(calc(var(--wm-amp) * -1));
    color: currentColor;
    filter: brightness(1.4);
  }
}

/* ---------- travelling underline highlight ----------
   A small 8 px dot rides under the wordmark, one pass per cycle. Adds the
   "alive" feel without being a typing effect. Position is interpolated by
   `left: 0% → 100%` over the same period the wave takes. */
.sweep {
  position: absolute;
  bottom: calc(var(--wm-amp) * 0.1);
  left: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.0;
  animation: wm-sweep 5s linear infinite;
}
@keyframes wm-sweep {
  0%   { left: 0%;   opacity: 0; }
  10%  { opacity: .7; }
  90%  { opacity: .7; }
  100% { left: 100%; opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .ch, .sweep { animation: none; }
}
</style>
