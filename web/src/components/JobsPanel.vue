<script setup>
import { computed } from 'vue'
import { useStudioStore } from '../stores/studio'
import JobCard from './JobCard.vue'

const store = useStudioStore()

const buckets = computed(() => {
  const active = []
  const done = []
  for (const j of store.jobList) {
    if (j.status === 'ready' || j.status === 'failed') done.push(j)
    else active.push(j)
  }
  return { active, done }
})
</script>

<template>
  <section class="panel card">
    <header class="head">
      <div class="head-text">
        <h2>Jobs</h2>
        <p class="hint">Live progress streamed from the GPU.</p>
      </div>
      <span class="pill" v-if="buckets.active.length">{{ buckets.active.length }} active</span>
    </header>

    <div class="list">
      <div v-if="buckets.active.length" class="group">
        <div class="group-label"><span>Active</span><span class="hr" /></div>
        <JobCard v-for="j in buckets.active" :key="j.id" :job="j" />
      </div>

      <div v-if="buckets.done.length" class="group">
        <div class="group-label"><span>Recent</span><span class="hr" /></div>
        <JobCard v-for="j in buckets.done" :key="j.id" :job="j" />
      </div>

      <div v-if="store.jobList.length === 0" class="empty">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 3l14 9-14 9V3z" />
        </svg>
        <strong>No jobs yet</strong>
        <span>Compose some text and hit Clone — it'll show up here in real time.</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: sticky;
  top: 80px;
  /* Fill the grid cell so the panel's footer aligns with the composer's. */
  height: 100%;
  max-height: calc(100vh - 100px);
}
.head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px;
}
.head h2 { font-size: 17px; }
.head-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.hint { color: var(--ink-3); margin: 0; font-size: 12.5px; }

.list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  flex: 1;
  margin: 0 -4px;
  padding: 2px 4px;
}
.group { display: flex; flex-direction: column; gap: 10px; }
.group-label {
  display: flex; align-items: center; gap: 8px;
  font-size: 11px;
  color: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 500;
}
.group-label .hr { flex: 1; height: 1px; background: var(--border-soft); }

.empty {
  margin: auto 0;
  text-align: center;
  padding: 28px 18px;
  border: 1px dashed var(--border);
  border-radius: var(--r-md);
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  color: var(--ink-3);
}
.empty svg { color: var(--ink-4); }
.empty strong { color: var(--ink); font-weight: 500; font-size: 13.5px; margin-top: 4px; }
.empty span { font-size: 12px; max-width: 32ch; line-height: 1.5; }

@media (max-width: 1024px) {
  .panel { position: static; max-height: none; }
}
</style>
