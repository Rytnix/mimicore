import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

/**
 * Drive a typing-on-mount animation for one or more strings. The composable
 * yields a reactive `text` ref and a `done` flag. Successive entries in
 * `lines` are typed one after another, separated by a configurable pause.
 * Honours `prefers-reduced-motion` by snapping straight to the final text.
 */
export function useTyped(lines, opts = {}) {
  const speed = opts.speed ?? 28        // ms per char
  const linePause = opts.linePause ?? 240
  const startDelay = opts.startDelay ?? 120

  const text = ref('')
  const done = ref(false)
  let timer = null
  let cancelled = false

  function reduce() {
    return typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }

  function run(arr) {
    if (reduce()) {
      text.value = arr.join('\n')
      done.value = true
      return
    }
    let li = 0
    let ci = 0
    let buf = ''
    function step() {
      if (cancelled) return
      const line = arr[li]
      if (line == null) { done.value = true; return }
      if (ci < line.length) {
        buf += line[ci]
        ci++
        text.value = buf
        timer = setTimeout(step, speed)
      } else {
        li++
        ci = 0
        if (li < arr.length) {
          buf += '\n'
          text.value = buf
          timer = setTimeout(step, linePause)
        } else {
          done.value = true
        }
      }
    }
    timer = setTimeout(step, startDelay)
  }

  onMounted(() => run(Array.isArray(lines) ? lines : [String(lines)]))
  onBeforeUnmount(() => { cancelled = true; if (timer) clearTimeout(timer) })

  return { text, done }
}
