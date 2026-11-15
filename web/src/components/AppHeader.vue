<script setup>
import { computed } from 'vue'
import { useStudioStore } from '../stores/studio'
import MimicoreLogo from './MimicoreLogo.vue'
import MimicoreWordmark from './MimicoreWordmark.vue'

const store = useStudioStore()

const activeJobs = computed(
  () => store.jobList.filter((j) => j.status === 'running' || j.status === 'queued').length,
)
</script>

<template>
  <header class="bar">
    <div class="brand">
      <MimicoreLogo :size="36" />
      <div class="title-stack">
        <MimicoreWordmark :size="18" :weight="700" />
        <div class="sub">Voice cloning, in any of 600+ languages.</div>
      </div>
    </div>

    <div class="status-row">
      <span class="pill" :class="{ ok: store.health.ok, err: !store.health.ok }">
        <span class="dot" /> server {{ store.health.ok ? 'online' : 'offline' }}
      </span>
      <span class="pill" :class="{ ok: store.health.cuda, warn: !store.health.cuda }">
        <span class="dot" /> {{ store.health.cuda ? 'CUDA' : 'CPU' }}
      </span>
      <span v-if="activeJobs" class="pill live">
        <span class="dot" /> {{ activeJobs }} running
      </span>

      <!-- User menu — only visible once authenticated. -->
      <div v-if="store.user" class="user-menu">
        <span class="user-name">{{ store.user.username }}</span>
        <button class="ghost xs" type="button" @click="store.logout">Sign out</button>
      </div>
    </div>
  </header>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 22px;
  border-bottom: 1px solid var(--border);
  background: rgba(244, 241, 234, 0.85);
  -webkit-backdrop-filter: saturate(140%) blur(14px);
  backdrop-filter: saturate(140%) blur(14px);
  position: sticky;
  top: 0;
  z-index: 20;
}
.brand { display: flex; align-items: center; gap: 12px; }
.title-stack h1 { font-size: 17px; font-weight: 600; letter-spacing: -0.02em; }
.sub { font-size: 11.5px; color: var(--ink-3); margin-top: 2px; letter-spacing: 0.02em; }

.status-row { display: flex; gap: 8px; align-items: center; }
.user-menu {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px 3px 12px;
  margin-left: 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
}
.user-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: -0.01em;
}

@media (max-width: 720px) {
  .bar { padding: 12px 16px; }
  .title-stack h1 { font-size: 15px; }
  .sub { display: none; }
}
</style>
