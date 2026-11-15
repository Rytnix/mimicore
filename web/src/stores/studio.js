import { defineStore } from 'pinia'
import { reactive, ref, computed } from 'vue'

const API = '/api'

export const useStudioStore = defineStore('studio', () => {
  /** Current signed-in user. null = anonymous (auth page shown). */
  const user = ref(null)
  const authChecked = ref(false)

  /** id -> ref dict from backend, plus client-side `liveSegments` */
  const refs = reactive({})
  /** id -> job dict, plus client-side `log` array */
  const jobs = reactive({})
  const selectedRefId = ref(null)
  const health = reactive({ ok: false, cuda: false })
  /** Full OmniVoice language catalogue, fetched once on boot. */
  const languages = ref([])
  const popularLanguages = ref([])
  /** The user's current target language. Drives synthesis, server-side
   *  Whisper hinting, and the browser's Web Speech API recognizer. Empty
   *  string = auto-detect. Lifted to the store so the composer's picker
   *  also affects the reference-panel mic recorder. */
  const targetLanguage = ref('')

  const refList = computed(() =>
    Object.values(refs).sort((a, b) => (a.uploaded_at < b.uploaded_at ? 1 : -1)),
  )
  const readyRefs = computed(() => refList.value.filter((r) => r.status === 'ready'))
  const jobList = computed(() =>
    Object.values(jobs).sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
  )
  const selectedRef = computed(() =>
    selectedRefId.value ? refs[selectedRefId.value] : null,
  )

  async function fetchMe() {
    try {
      const r = await fetch(`${API}/auth/me`, { credentials: 'same-origin' })
      const j = await r.json()
      user.value = j.user || null
    } catch {
      user.value = null
    } finally {
      authChecked.value = true
    }
    return user.value
  }

  async function login(username, password) {
    const r = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ username, password }),
    })
    if (!r.ok) {
      const text = await r.text()
      throw new Error(text || `login failed (${r.status})`)
    }
    const j = await r.json()
    user.value = j.user
    return j.user
  }

  async function register(username, password) {
    const r = await fetch(`${API}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ username, password }),
    })
    if (!r.ok) {
      const text = await r.text()
      throw new Error(text || `register failed (${r.status})`)
    }
    const j = await r.json()
    user.value = j.user
    return j.user
  }

  async function logout() {
    try { await fetch(`${API}/auth/logout`, { method: 'POST', credentials: 'same-origin' }) }
    catch {}
    user.value = null
    // Clear cached state so next user doesn't see the previous one's data.
    for (const k of Object.keys(refs)) delete refs[k]
    for (const k of Object.keys(jobs)) delete jobs[k]
    selectedRefId.value = null
  }

  async function checkHealth() {
    try {
      const r = await fetch(`${API}/health`)
      const j = await r.json()
      Object.assign(health, j)
    } catch {
      health.ok = false
    }
  }

  async function loadLanguages() {
    if (languages.value.length) return
    try {
      const r = await fetch(`${API}/languages`)
      const j = await r.json()
      languages.value = j.languages || []
      popularLanguages.value = j.popular || []
    } catch {
      languages.value = []
      popularLanguages.value = []
    }
  }

  async function loadAll() {
    const [r1, r2] = await Promise.all([
      fetch(`${API}/refs`).then((r) => r.json()),
      fetch(`${API}/jobs`).then((r) => r.json()),
    ])
    for (const r of r1) refs[r.id] = { ...refs[r.id], ...r }
    for (const j of r2) jobs[j.id] = { ...jobs[j.id], ...j, log: j.log || [] }
    if (!selectedRefId.value && r1.length) {
      const ready = r1.find((r) => r.status === 'ready') || r1[0]
      selectedRefId.value = ready.id
    }
  }

  async function uploadRef(file) {
    const fd = new FormData()
    fd.append('file', file)
    // Hint the language so the server-side Whisper doesn't, e.g.,
    // mistake Hindi for Urdu.
    const url = targetLanguage.value
      ? `${API}/refs?language=${encodeURIComponent(targetLanguage.value)}`
      : `${API}/refs`
    const r = await fetch(url, { method: 'POST', body: fd })
    if (!r.ok) throw new Error(`upload failed: ${r.status} ${await r.text()}`)
    const ref = await r.json()
    refs[ref.id] = { ...ref, liveSegments: [] }
    if (!selectedRefId.value) selectedRefId.value = ref.id
    streamRefTranscript(ref.id)
    return ref
  }

  async function deleteRef(id) {
    await fetch(`${API}/refs/${id}`, { method: 'DELETE' })
    delete refs[id]
    if (selectedRefId.value === id) {
      selectedRefId.value = readyRefs.value[0]?.id || refList.value[0]?.id || null
    }
  }

  function streamRefTranscript(id) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}${API}/refs/${id}/transcribe`)
    const ref = refs[id] || (refs[id] = {})
    ref.liveSegments = ref.liveSegments || []

    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data)
      if (m.type === 'snapshot') {
        ref.status = m.status
        ref.transcript = m.transcript
        ref.segments = m.segments
        ref.liveSegments = [...(m.segments || [])]
        ref.language = m.language
      } else if (m.type === 'status') {
        ref.status = m.status
      } else if (m.type === 'segment') {
        ref.liveSegments = [...(ref.liveSegments || []), m.segment]
        ref.transcript = (ref.transcript ? ref.transcript + ' ' : '') + m.segment.text
        ref.language = m.language
      } else if (m.type === 'done') {
        ref.status = 'ready'
        ref.transcript = m.transcript
        ref.segments = m.segments
      } else if (m.type === 'error') {
        ref.status = 'error'
        ref.error = m.error
      }
    }
    ws.onerror = () => { /* swallow; status reflects whatever last arrived */ }
  }

  async function generateScript(prompt) {
    const r = await fetch(`${API}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    })
    if (!r.ok) throw new Error(`generate failed: ${r.status} ${await r.text()}`)
    return r.json()
  }

  async function transcribeBlob(blob, filename = 'dictation.webm') {
    const fd = new FormData()
    fd.append('file', blob, filename)
    const url = targetLanguage.value
      ? `${API}/transcribe?language=${encodeURIComponent(targetLanguage.value)}`
      : `${API}/transcribe`
    const r = await fetch(url, { method: 'POST', body: fd })
    if (!r.ok) throw new Error(`transcribe failed: ${r.status} ${await r.text()}`)
    return r.json()
  }

  async function createJob(payload) {
    const r = await fetch(`${API}/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!r.ok) throw new Error(`create job failed: ${r.status} ${await r.text()}`)
    const job = await r.json()
    jobs[job.id] = { ...job, log: [...(job.log || [])] }
    streamJob(job.id)
    return job
  }

  function streamJob(id) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}${API}/jobs/${id}/stream`)
    const job = jobs[id] || (jobs[id] = { id, log: [] })

    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data)
      if (m.type === 'snapshot') {
        job.status = m.status
        job.log = [...(m.log || [])]
        job.wait_reason = m.wait_reason
        job.queue_position = m.queue_position
        job.running = m.running
        job.max_parallel = m.max_parallel
      } else if (m.type === 'status') {
        job.status = m.status
        if (m.status === 'running') job.wait_reason = null
      } else if (m.type === 'wait') {
        job.wait_reason = m.reason
        job.queue_position = m.queue_position
        job.running = m.running
        job.max_parallel = m.max_parallel
        job.free_vram_mb = m.free_vram_mb
      } else if (m.type === 'stage') {
        job.stage = m.stage
      } else if (m.type === 'log') {
        job.log = [...(job.log || []), m.line]
      } else if (m.type === 'done') {
        job.status = 'ready'
        job.duration = m.duration
        job.output_url = m.output_url
      } else if (m.type === 'failed') {
        job.status = 'failed'
        job.return_code = m.return_code
      } else if (m.type === 'error') {
        job.status = 'failed'
        job.error = m.error
      }
    }
  }

  function selectRef(id) {
    selectedRefId.value = id
  }

  return {
    refs, jobs, health,
    user, authChecked,
    languages, popularLanguages, targetLanguage,
    refList, readyRefs, jobList,
    selectedRefId, selectedRef,
    fetchMe, login, register, logout,
    checkHealth, loadAll, loadLanguages,
    uploadRef, deleteRef, streamRefTranscript,
    transcribeBlob, generateScript,
    createJob, streamJob, selectRef,
  }
})
