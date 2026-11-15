<script setup>
defineProps({
  size: { type: Number, default: 36 },
  /** When true, no dark tile background — just the marks. Use for
   *  watermarks or anywhere a transparent/colored variant is needed. */
  bare: { type: Boolean, default: false },
})
</script>

<template>
  <span
    class="logo"
    :class="{ bare }"
    :style="{ width: size + 'px', height: size + 'px' }"
    aria-label="Mimicore"
  >
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="mc-glow" cx="0.5" cy="0.5" r="0.55">
          <stop offset="0%" stop-color="#ffffff" stop-opacity=".22" />
          <stop offset="60%" stop-color="#ffffff" stop-opacity="0" />
        </radialGradient>
      </defs>

      <!-- Tile body — only in the badge variant -->
      <template v-if="!bare">
        <rect x="0" y="0" width="64" height="64" rx="14" fill="#0A0A0A" />
        <rect x="0" y="0" width="64" height="64" rx="14" fill="url(#mc-glow)" />
      </template>

      <!-- Slow rotating outer ring with broken segments. -->
      <g class="ring">
        <circle cx="32" cy="32" r="22" fill="none" stroke="currentColor"
                stroke-opacity=".22" stroke-width="1" stroke-dasharray="3 6" />
      </g>

      <!-- Three offset waveforms.
           The animation flows energy along each path via stroke-dashoffset
           — much smoother than the old scaleY breathing, which collapsed
           the wave to nearly flat at the midpoint. The dash period (14+12
           = 26) and the offset target (-26) match exactly so the loop is
           seamless.  pathLength="100" is set so the dash numbers don't
           depend on the actual path length. -->
      <g class="waves">
        <path class="wave w1" d="M14 32 Q 22 18 32 32 T 50 32" pathLength="100"
              stroke="currentColor" />
        <path class="wave w2" d="M14 32 Q 22 46 32 32 T 50 32" pathLength="100"
              stroke="currentColor" stroke-opacity=".55" />
        <path class="wave w3" d="M14 32 Q 22 26 32 32 T 50 32" pathLength="100"
              stroke="currentColor" stroke-opacity=".30" />
      </g>

      <!-- Pulsing centre node — the "core" -->
      <circle class="core" cx="32" cy="32" r="2.4" fill="currentColor" />
    </svg>
  </span>
</template>

<style scoped>
.logo {
  display: inline-block;
  position: relative;
  /* Default (badge) variant: white marks on the black tile, soft glow. */
  color: #FFFFFF;
  border-radius: 14px;
  overflow: hidden;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.12),
    0 6px 18px -6px rgba(10, 10, 10, .55),
    0 1px 2px rgba(10, 10, 10, .25);
}
/* Bare variant: just the marks, no tile, no shadow. The host (e.g. a
   watermark wrapper) controls colour via `color:` and opacity. */
.logo.bare {
  color: var(--ink);
  border-radius: 0;
  overflow: visible;
  box-shadow: none;
  background: transparent;
}
.logo svg { display: block; width: 100%; height: 100%; }

/* ---------- ring ---------- */
.ring { transform-origin: 32px 32px; animation: mc-spin 14s linear infinite; }
@keyframes mc-spin { to { transform: rotate(360deg); } }

/* ---------- waves: stroke-dash flow (seamless) ---------- */
.waves path {
  fill: none;
  stroke-width: 1.8;
  stroke-linecap: round;
  /* dash-period = 14 + 12 = 26  →  shifting offset by exactly -26 lands
     back on itself, so the animation never "snaps". */
  stroke-dasharray: 14 12;
  animation-name: mc-flow;
  animation-iteration-count: infinite;
  animation-timing-function: linear;
}
.wave.w1 { animation-duration: 3.6s; }
.wave.w2 { animation-duration: 4.8s; animation-direction: reverse; }
.wave.w3 { animation-duration: 6.0s; }
@keyframes mc-flow { to { stroke-dashoffset: -26; } }

/* ---------- core ---------- */
.core { transform-origin: 32px 32px; transform-box: fill-box; animation: mc-core 2.4s ease-in-out infinite; }
@keyframes mc-core {
  0%, 100% { transform: scale(.85); opacity: .85; }
  50%      { transform: scale(1.35); opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .ring, .waves path, .core { animation: none; }
}
</style>
