<script setup>
import { onMounted, ref, watch } from 'vue'
import { useStudioStore } from './stores/studio'
import AppHeader from './components/AppHeader.vue'
import ReferencePanel from './components/ReferencePanel.vue'
import ComposerPanel from './components/ComposerPanel.vue'
import JobsPanel from './components/JobsPanel.vue'
import LoginPage from './components/LoginPage.vue'
import RegisterPage from './components/RegisterPage.vue'

const store = useStudioStore()
// Local auth-page mode toggle; LoginPage and RegisterPage emit 'switch-mode'.
const authMode = ref('login')

async function bootForUser() {
  await store.checkHealth()
  await Promise.all([store.loadAll(), store.loadLanguages()])
  for (const r of store.refList) {
    if (r.status === 'transcribing' || r.status === 'queued') store.streamRefTranscript(r.id)
  }
  for (const j of store.jobList) {
    if (j.status === 'queued' || j.status === 'running') store.streamJob(j.id)
  }
}

onMounted(async () => {
  await store.fetchMe()
  if (store.user) await bootForUser()
})

// Re-boot data when the user signs in / changes.
watch(() => store.user?.id, (id, prev) => {
  if (id && id !== prev) bootForUser()
})
</script>

<template>
  <!-- While we're checking the cookie, render nothing rather than flash the
       login form on top of an authenticated session. -->
  <div v-if="!store.authChecked" class="boot" />

  <template v-else-if="!store.user">
    <LoginPage    v-if="authMode === 'login'"    @switch-mode="authMode = $event" />
    <RegisterPage v-else                          @switch-mode="authMode = $event" />
  </template>

  <div v-else class="shell">
    <AppHeader />
    <main class="grid">
      <ReferencePanel class="col col-left" />
      <ComposerPanel class="col col-mid" />
      <JobsPanel class="col col-right" />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
/* Fullfilling: no max-width, edge-to-edge horizontally so the UI uses the
   whole viewport on wide displays. Vertical padding is preserved so cards
   don't kiss the sticky header / window chrome. */
.grid {
  flex: 1;
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr) 400px;
  gap: 18px;
  padding: 18px 18px 24px;
  width: 100%;
  align-items: stretch;
}
.col { min-width: 0; }

@media (max-width: 1280px) {
  .grid { grid-template-columns: 320px minmax(0, 1fr) 360px; gap: 14px; padding: 14px 14px 22px; }
}
@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; }
  .col { min-height: 0; }
}
@media (max-width: 720px) {
  .grid { padding: 12px 10px 18px; gap: 12px; }
}
</style>
