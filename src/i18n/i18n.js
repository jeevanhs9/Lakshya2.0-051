import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'
import { DEFAULT_LANGUAGE, languageByCode } from './languages'

import en from './locales/en.json'
import kn from './locales/kn.json'
import hi from './locales/hi.json'
import te from './locales/te.json'
import ta from './locales/ta.json'
import ml from './locales/ml.json'
import mr from './locales/mr.json'
import bn from './locales/bn.json'
import gu from './locales/gu.json'
import pa from './locales/pa.json'
import or from './locales/or.json'
import as from './locales/as.json'
import ur from './locales/ur.json'
import enCheckout from './locales/en-checkout.json'
import knCheckout from './locales/kn-checkout.json'
import enLogin from './locales/en-login.json'
import knLogin from './locales/kn-login.json'
import enShell from './locales/en-shell.json'
import knShell from './locales/kn-shell.json'
import enDashboard from './locales/en-dashboard.json'
import knDashboard from './locales/kn-dashboard.json'

// Every locale inherits the complete English key set. This gives farmers a
// readable fallback while regional copy is expanded and reviewed.
const withEnglishFallback = (locale) => ({
  ...en,
  ...locale,
  ui: { ...en.ui, ...locale.ui },
})

// i18next uses the default "translation" namespace. Locale JSON keeps its
// application keys at the root, so each resource must be wrapped once here.
const resource = (locale, extras = {}) => ({
  translation: {
    ...locale,
    ...extras,
    ui: { ...locale.ui, ...extras.ui },
  },
})

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: resource(en, { ...enCheckout, ...enLogin, ...enShell, ...enDashboard }),
      kn: resource(withEnglishFallback(kn), { ...enCheckout, ...knCheckout, ...enLogin, ...knLogin, ...enShell, ...knShell, ...enDashboard, ...knDashboard }),
      hi: resource(withEnglishFallback(hi), { ...enCheckout, ...enLogin, ...enShell, ...enDashboard }), te: resource(withEnglishFallback(te), { ...enCheckout, ...enLogin, ...enShell, ...enDashboard }),
      ta: resource(withEnglishFallback(ta), { ...enCheckout, ...enLogin, ...enShell, ...enDashboard }), ml: resource(withEnglishFallback(ml), { ...enCheckout, ...enLogin, ...enShell, ...enDashboard }), mr: resource(withEnglishFallback(mr), { ...enCheckout, ...enLogin, ...enShell, ...enDashboard }),
      bn: resource(withEnglishFallback(bn), { ...enShell, ...enDashboard }), gu: resource(withEnglishFallback(gu), { ...enShell, ...enDashboard }), pa: resource(withEnglishFallback(pa), { ...enShell, ...enDashboard }),
      or: resource(withEnglishFallback(or), { ...enShell, ...enDashboard }), as: resource(withEnglishFallback(as), { ...enShell, ...enDashboard }), ur: resource(withEnglishFallback(ur), { ...enShell, ...enDashboard }),
    },
    fallbackLng: DEFAULT_LANGUAGE,
    supportedLngs: ['en', 'kn', 'hi', 'te', 'ta', 'ml', 'mr', 'bn', 'gu', 'pa', 'or', 'as', 'ur'],
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'farmlink-language',
      caches: ['localStorage'],
    },
    react: { useSuspense: false },
  })

// Keep language metadata (including Urdu RTL) in sync without modifying page
// text outside React. All visible text must come from explicit t() keys.
i18n.on('languageChanged', (code) => {
  const language = languageByCode(code)
  document.documentElement.lang = language.code
  document.documentElement.dir = language.dir
})

export default i18n
