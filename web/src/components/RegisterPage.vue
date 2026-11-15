<script setup>
import { ref } from 'vue'
import { useStudioStore } from '../stores/studio'
import AuthShell from './AuthShell.vue'

const emit = defineEmits(['switch-mode'])

const store = useStudioStore()
const username = ref('')
const password = ref('')
const confirm = ref('')
const busy = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!username.value.trim() || !password.value) {
    error.value = 'Username and password required.'
    return
  }
  if (password.value !== confirm.value) {
    error.value = 'Passwords don’t match.'
    return
  }
  busy.value = true
  try {
    await store.register(username.value.trim(), password.value)
  } catch (e) {
    error.value = String(e.message || e).replace(/^.*"detail":"|"\}$/g, '')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthShell
    mode="register"
    title="Create an account"
    sub="Your reference audio and clones live in your account, private to you."
    @switch-mode="emit('switch-mode', $event)"
  >
    <form class="form" @submit.prevent="submit">
      <label class="field">
        <span>Username</span>
        <input v-model="username" type="text" autocomplete="username" autofocus />
      </label>
      <label class="field">
        <span>Password</span>
        <input v-model="password" type="password" autocomplete="new-password" />
      </label>
      <label class="field">
        <span>Confirm password</span>
        <input v-model="confirm" type="password" autocomplete="new-password" />
      </label>

      <div v-if="error" class="error-msg">{{ error }}</div>

      <button class="primary big" type="submit" :disabled="busy">
        <span v-if="busy" class="spin" aria-hidden="true" />
        {{ busy ? 'Creating account…' : 'Create an account' }}
      </button>
    </form>

    <template #foot>
      <span>Already have an account?</span>
      <button class="link" type="button" @click="emit('switch-mode', 'login')">Sign in →</button>
    </template>
  </AuthShell>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: 10px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field span {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-weight: 600;
  color: var(--ink-3);
}
.field input {
  border-radius: 12px;
  padding: 12px 14px;
  font-size: 14px;
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid rgba(10, 10, 10, 0.08);
  -webkit-backdrop-filter: blur(8px);
          backdrop-filter: blur(8px);
}
.field input:focus { background: rgba(255, 255, 255, 0.92); }

.primary.big {
  margin-top: 6px;
  padding: 12px 18px;
  font-size: 14px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.spin {
  width: 13px; height: 13px;
  border: 2px solid rgba(255,255,255,.25);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.error-msg {
  background: var(--err-soft);
  color: #7F1D1D;
  padding: 8px 10px;
  border-radius: 10px;
  font-size: 12.5px;
  border: 1px solid rgba(239, 68, 68, .35);
}

.link {
  background: transparent; border: 0; padding: 0;
  color: var(--ink); font-weight: 600;
  cursor: pointer; font-size: inherit;
  margin-left: 6px;
}
.link:hover { text-decoration: underline; }
</style>
