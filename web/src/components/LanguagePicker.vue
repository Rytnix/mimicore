<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useStudioStore } from '../stores/studio'

const props = defineProps({
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const store = useStudioStore()
const open = ref(false)
const query = ref('')
const rootEl = ref(null)
const triggerEl = ref(null)
const popEl = ref(null)
const inputEl = ref(null)
const activeIdx = ref(0)
// Viewport-relative position for the teleported popover. Recomputed on open
// and on scroll/resize so the menu stays glued to the trigger.
const popPos = ref({ top: 0, left: 0, width: 380 })

const allLangs = computed(() => store.languages)

// Display label for the currently selected code. Falls back to the raw code
// if the catalogue hasn't loaded yet (e.g. server still spinning up).
const currentLabel = computed(() => {
  if (!props.modelValue) return 'Auto-detect'
  const hit = allLangs.value.find((l) => l.code === props.modelValue)
  return hit ? hit.name : props.modelValue.toUpperCase()
})

const popularItems = computed(() => {
  const codes = store.popularLanguages || []
  const map = new Map(allLangs.value.map((l) => [l.code, l]))
  return codes.map((c) => map.get(c)).filter(Boolean)
})

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return allLangs.value
  // Match either the start of the language name (preferred) or anywhere in
  // the name/code. Sort prefix matches first so typing "en" surfaces "English"
  // before "Bengali".
  const prefix = []
  const sub = []
  for (const l of allLangs.value) {
    const name = l.name.toLowerCase()
    const code = l.code.toLowerCase()
    if (name.startsWith(q) || code === q) prefix.push(l)
    else if (name.includes(q) || code.includes(q)) sub.push(l)
  }
  return [...prefix, ...sub]
})

watch(filtered, () => { activeIdx.value = 0 })

function pick(code) {
  emit('update:modelValue', code)
  close()
}

function clear() {
  emit('update:modelValue', '')
  close()
}

function updatePopPos() {
  const el = triggerEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const desired = 380
  const margin = 12
  const width = Math.min(desired, window.innerWidth - margin * 2)
  // Right-align the popover with the trigger, but keep it on-screen.
  let left = r.right - width
  if (left < margin) left = margin
  if (left + width > window.innerWidth - margin) left = window.innerWidth - margin - width
  popPos.value = { top: r.bottom + 8, left, width }
}

async function toggle() {
  if (open.value) { close(); return }
  open.value = true
  updatePopPos()
  await nextTick()
  inputEl.value?.focus()
}

function close() {
  open.value = false
  query.value = ''
  activeIdx.value = 0
}

function onKeydown(e) {
  if (!open.value) return
  if (e.key === 'Escape') { e.preventDefault(); close(); return }
  const list = filtered.value
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIdx.value = Math.min(activeIdx.value + 1, list.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIdx.value = Math.max(activeIdx.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const target = list[activeIdx.value]
    if (target) pick(target.code)
  }
}

function onDocClick(e) {
  if (!open.value) return
  // The popover lives in <body> via teleport, so check both anchors.
  const inTrigger = rootEl.value && rootEl.value.contains(e.target)
  const inPop = popEl.value && popEl.value.contains(e.target)
  if (!inTrigger && !inPop) close()
}

function onViewportChange() {
  if (open.value) updatePopPos()
}

onMounted(() => {
  document.addEventListener('mousedown', onDocClick)
  window.addEventListener('scroll', onViewportChange, true)
  window.addEventListener('resize', onViewportChange)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocClick)
  window.removeEventListener('scroll', onViewportChange, true)
  window.removeEventListener('resize', onViewportChange)
})
</script>

<template>
  <div class="lp" ref="rootEl">
    <button type="button" class="lp-trigger glass" :class="{ active: open }" @click="toggle" ref="triggerEl">
      <span class="lp-icon" aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9"/>
          <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>
        </svg>
      </span>
      <span class="lp-label">
        <span class="lp-kicker">Language</span>
        <span class="lp-current">{{ currentLabel }}</span>
      </span>
      <span class="lp-caret" aria-hidden="true">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m6 9 6 6 6-6"/>
        </svg>
      </span>
    </button>

    <Teleport to="body">
    <div
      v-if="open"
      ref="popEl"
      class="lp-pop glass-pop"
      :style="{ top: popPos.top + 'px', left: popPos.left + 'px', width: popPos.width + 'px' }"
    >
      <div class="lp-search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>
        </svg>
        <input
          ref="inputEl"
          v-model="query"
          type="text"
          :placeholder="`Search ${allLangs.length || 600}+ languages…`"
          @keydown="onKeydown"
        />
        <button v-if="modelValue" class="lp-clear ghost xs" @click="clear">Auto</button>
      </div>

      <div class="lp-body">
        <div v-if="!query && popularItems.length" class="lp-section">
          <div class="lp-section-label">Popular</div>
          <div class="lp-chips">
            <button
              v-for="l in popularItems"
              :key="l.code"
              type="button"
              class="lp-chip"
              :class="{ on: l.code === modelValue }"
              @click="pick(l.code)"
            >
              {{ l.name }}
              <span class="lp-code">{{ l.code }}</span>
            </button>
          </div>
        </div>

        <div class="lp-section">
          <div class="lp-section-label">
            {{ query ? `Matches (${filtered.length})` : 'All languages' }}
          </div>
          <ul class="lp-list" role="listbox">
            <li
              v-for="(l, i) in filtered"
              :key="l.code"
              role="option"
              :aria-selected="l.code === modelValue"
              :class="{ on: l.code === modelValue, active: i === activeIdx }"
              @click="pick(l.code)"
              @mouseenter="activeIdx = i"
            >
              <span class="lp-name">{{ l.name }}</span>
              <span class="lp-code">{{ l.code }}</span>
            </li>
            <li v-if="filtered.length === 0" class="lp-empty">
              No language matches “{{ query }}”.
            </li>
          </ul>
        </div>
      </div>

      <div class="lp-foot">
        <span>
          OmniVoice supports
          <strong>{{ allLangs.length || '600+' }}</strong> languages.
        </span>
        <button class="ghost xs" @click="clear">Auto-detect</button>
      </div>
    </div>
    </Teleport>
  </div>
</template>

<style scoped>
.lp { position: relative; min-width: 0; }

.lp-trigger {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 14px;
  font-size: 13px;
  text-align: left;
  min-width: 180px;
}
.lp-icon { color: var(--accent); display: inline-flex; }
.lp-label { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.lp-kicker {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  font-weight: 600;
}
.lp-current {
  font-size: 13px;
  color: var(--ink);
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.lp-caret { color: var(--ink-3); transition: transform .15s var(--ease); }
.lp-trigger.active .lp-caret { transform: rotate(180deg); }

/* Teleported to <body> — fixed positioning escapes the composer card's
   stacking context so the menu always paints above the textarea. */
.lp-pop {
  position: fixed;
  z-index: 1000;
  border-radius: 18px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  max-height: min(460px, calc(100vh - 32px));
  animation: lp-pop .18s var(--ease) both;
}
@keyframes lp-pop {
  from { opacity: 0; transform: translateY(-6px) scale(.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.lp-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.6);
  color: var(--ink-3);
}
.lp-search input {
  flex: 1;
  border: 0;
  background: transparent;
  padding: 4px 0;
  font-size: 13px;
  outline: none;
  color: var(--ink);
}
.lp-search input::placeholder { color: var(--ink-4); }
.lp-clear { padding: 2px 8px !important; font-size: 11px !important; }

.lp-body {
  flex: 1;
  overflow-y: auto;
  padding: 6px 4px 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.lp-section { display: flex; flex-direction: column; gap: 6px; }
.lp-section-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  padding: 0 8px;
  font-weight: 600;
}

.lp-chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 4px; }
.lp-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: rgba(255, 255, 255, 0.6);
  color: var(--ink-2);
}
.lp-chip:hover { background: rgba(255, 255, 255, 0.85); }
.lp-chip.on {
  background: var(--accent);
  color: var(--accent-ink);
  border-color: var(--accent);
}
.lp-chip.on .lp-code { color: rgba(255,255,255,.75); }
.lp-chip .lp-code { font-family: var(--mono); font-size: 10px; color: var(--ink-4); }

.lp-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; }
.lp-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 10px;
  cursor: pointer;
  font-size: 13px;
  color: var(--ink);
  transition: background .12s var(--ease);
}
.lp-list li.active { background: rgba(255, 255, 255, 0.7); }
.lp-list li.on {
  background: var(--accent-soft);
  color: var(--accent-hover);
}
.lp-list li.on .lp-code { color: var(--accent); }
.lp-list .lp-code {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-4);
}
.lp-empty {
  padding: 14px 10px;
  text-align: center;
  color: var(--ink-3);
  font-size: 12px;
}

.lp-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 4px;
  border-top: 1px solid rgba(0,0,0,.05);
  font-size: 11.5px;
  color: var(--ink-3);
}
</style>
