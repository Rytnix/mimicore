// Map our internal language code (mostly ISO 639-1, plus a few OmniVoice
// dialect codes) to a BCP 47 tag the browser's Web Speech API will accept.
// Browsers ARE picky here: "hi" alone fails on Chrome on some platforms,
// "hi-IN" works. So we always pin a sensible region for popular cases.
const BCP47 = {
  en: 'en-US', es: 'es-ES', fr: 'fr-FR', de: 'de-DE', it: 'it-IT',
  pt: 'pt-BR', ru: 'ru-RU', zh: 'zh-CN', ja: 'ja-JP', ko: 'ko-KR',
  hi: 'hi-IN', bn: 'bn-IN', ur: 'ur-PK', tr: 'tr-TR', vi: 'vi-VN',
  id: 'id-ID', th: 'th-TH', fa: 'fa-IR', pl: 'pl-PL', nl: 'nl-NL',
  uk: 'uk-UA', sv: 'sv-SE', fi: 'fi-FI', he: 'he-IL', el: 'el-GR',
  cs: 'cs-CZ', ro: 'ro-RO', hu: 'hu-HU', da: 'da-DK', ms: 'ms-MY',
  sw: 'sw-KE', ta: 'ta-IN', te: 'te-IN', mr: 'mr-IN', ml: 'ml-IN',
  pa: 'pa-IN', gu: 'gu-IN', kn: 'kn-IN', my: 'my-MM', am: 'am-ET',
  // OmniVoice's Arabic dialect codes → Web Speech regional tags.
  arz: 'ar-EG', arq: 'ar-DZ', shu: 'ar-TD',
}

export function toBcp47(code) {
  if (!code) return 'en-US'
  const c = code.toLowerCase()
  return BCP47[c] || c
}
