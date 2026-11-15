<script setup>
import MimicoreLogo from './MimicoreLogo.vue'
import MimicoreWordmark from './MimicoreWordmark.vue'

defineProps({
  /** Active tab: 'login' or 'register'. */
  mode:  { type: String, default: 'login' },
  /** Headline shown under the centre brand mark. */
  title: { type: String, default: '' },
  sub:   { type: String, default: '' },
})
const emit = defineEmits(['switch-mode'])
</script>

<template>
  <div class="auth-page">
    <!-- Light backdrop: warm paper, soft radial accents, hairline grid. -->
    <div class="auth-bg" aria-hidden="true" />

    <!-- Top-left brand stub — small logo + animated wordmark. -->
    <header class="brand-stub" aria-label="Mimicore">
      <MimicoreLogo :size="32" />
      <MimicoreWordmark :size="15" :weight="700" />
    </header>

    <!-- Giant logo bloom behind the card. Same component, bare variant,
         heavily de-saturated so the marks read as a watermark, not chrome. -->
    <div class="watermark" aria-hidden="true">
      <MimicoreLogo :size="640" bare />
    </div>

    <!-- Transparent glass card -->
    <main class="auth-card">
      <!-- Card-centre brand mark: the same logo, just bigger, with the
           animated wordmark right under it. -->
      <div class="card-mark">
        <MimicoreLogo :size="64" />
        <MimicoreWordmark :size="22" :weight="800" />
      </div>

      <!-- Tab pill: Sign up | Sign in -->
      <div class="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          :aria-selected="mode === 'register'"
          :class="{ on: mode === 'register' }"
          @click="emit('switch-mode', 'register')"
        >Sign up</button>
        <button
          type="button"
          role="tab"
          :aria-selected="mode === 'login'"
          :class="{ on: mode === 'login' }"
          @click="emit('switch-mode', 'login')"
        >Sign in</button>
      </div>

      <h1 v-if="title" class="title">{{ title }}</h1>
      <p   v-if="sub"   class="sub">{{ sub }}</p>

      <section class="body">
        <slot />
      </section>

      <footer class="foot">
        <slot name="foot" />
      </footer>
    </main>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px 16px;
  position: relative;
  overflow: hidden;
}

/* Warm-paper backdrop with soft accents + the same 80 px hairline grid as
   the main app. Keeps the auth flow visually tied to the studio. */
.auth-bg {
  position: absolute; inset: 0;
  pointer-events: none;
  background:
    radial-gradient(900px 700px at 12% -10%, rgba(10,10,10,.05) 0%, transparent 55%),
    radial-gradient(900px 700px at 110% 110%, rgba(10,10,10,.04) 0%, transparent 55%),
    linear-gradient(180deg, #F4F1EA 0%, #ECE5D5 100%);
}
.auth-page::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(10, 10, 10, .045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(10, 10, 10, .045) 1px, transparent 1px);
  background-size: 80px 80px;
}

/* ---------- top-left brand stub ---------- */
.brand-stub {
  position: absolute;
  top: 22px;
  left: 22px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  z-index: 5;
}

/* ---------- giant watermark ---------- */
.watermark {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
  /* Watermark colour and opacity. Marks pick this up via currentColor. */
  color: var(--ink);
  opacity: 0.08;
  /* Slow ambient drift so the watermark feels alive even from the back of
     the page — combined with the in-mark animations the whole thing reads
     as one large breathing brand. */
  animation: wm-drift 16s ease-in-out infinite;
}
@keyframes wm-drift {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50%      { transform: translate(0, -8px) scale(1.02); }
}

/* ---------- glass card ---------- */
.auth-card {
  position: relative;
  z-index: 3;
  width: min(440px, 92vw);
  padding: 26px 30px 22px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  /* Transparent glass: light fill + heavy backdrop blur. The watermark
     behind shows through softly. */
  background: rgba(255, 255, 255, 0.40);
  border: 1px solid rgba(10, 10, 10, 0.08);
  border-radius: 22px;
  -webkit-backdrop-filter: saturate(160%) blur(20px);
          backdrop-filter: saturate(160%) blur(20px);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.7),
    0 30px 60px -22px rgba(10, 10, 10, .25),
    0 6px 14px rgba(10, 10, 10, .06);
  animation: card-in .55s cubic-bezier(.22, 1, .36, 1) both;
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(8px) scale(.98); }
  to   { opacity: 1; transform: none; }
}

/* ---------- card-centre brand mark ---------- */
.card-mark {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  margin-bottom: 4px;
}

/* ---------- tabs ---------- */
.tabs {
  align-self: center;
  display: inline-flex;
  padding: 4px;
  background: rgba(10, 10, 10, 0.06);
  border-radius: 999px;
  border: 1px solid rgba(10, 10, 10, 0.08);
}
.tabs button {
  padding: 6px 14px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  font-family: var(--sans);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-3);
  cursor: pointer;
  transition: background .18s var(--ease), color .18s var(--ease);
}
.tabs button:hover { color: var(--ink); }
.tabs button.on {
  background: var(--ink);
  color: #fff;
  box-shadow: 0 6px 18px -8px rgba(10, 10, 10, .55);
}

.title {
  font-family: var(--sans);
  font-weight: 800;
  font-size: 22px;
  letter-spacing: -0.025em;
  text-align: center;
  margin: 4px 0 0;
}
.sub {
  text-align: center;
  margin: -2px 0 4px;
  color: var(--ink-3);
  font-size: 13px;
  max-width: 32ch;
  align-self: center;
}

.body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.foot {
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px solid rgba(10, 10, 10, 0.08);
  font-size: 12.5px;
  color: var(--ink-3);
  text-align: center;
}

@media (max-width: 480px) {
  .brand-stub { top: 14px; left: 14px; }
}
@media (prefers-reduced-motion: reduce) {
  .watermark, .auth-card { animation: none; }
}
</style>
