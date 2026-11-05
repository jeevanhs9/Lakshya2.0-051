import { Check, Languages, Search, X } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LANGUAGES, languageByCode } from '../../i18n/languages'

export default function LanguageSelector() {
  const { i18n, t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef(null)
  const active = languageByCode(i18n.resolvedLanguage || i18n.language)
  const languages = useMemo(() => LANGUAGES.filter((language) => {
    const value = query.trim().toLocaleLowerCase()
    return !value || language.nativeName.toLocaleLowerCase().includes(value) || language.englishName.toLocaleLowerCase().includes(value)
  }), [query])
  const choose = async (code) => {
    await i18n.changeLanguage(code)
    window.localStorage.setItem('farmlink-language', code)
    setOpen(false)
    setQuery('')
  }

  return <div className="relative">
    <button type="button" onClick={() => { setOpen((value) => !value); window.setTimeout(() => inputRef.current?.focus(), 0) }} className="inline-flex items-center gap-1.5 rounded-full p-2 text-ink-700 transition-colors hover:bg-leaf-50 hover:text-forest-700 focus-ring" aria-label={t('ui.selectLanguage')} aria-expanded={open} aria-haspopup="dialog">
      <Languages size={20} />
      <span className="hidden max-w-20 truncate text-xs font-bold sm:inline">{active.nativeName}</span>
    </button>
    {open && <div className="absolute right-0 top-12 z-50 w-[min(21rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border border-ink-100 bg-white shadow-2xl" role="dialog" aria-label={t('ui.selectLanguage')}>
      <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3"><div><p className="text-sm font-bold text-ink-900">{t('ui.selectLanguage')}</p><p className="text-xs text-ink-500">{active.nativeName} · {active.englishName}</p></div><button type="button" className="rounded-full p-1.5 text-ink-500 hover:bg-ink-100 focus-ring" onClick={() => setOpen(false)} aria-label={t('ui.close')}><X size={16} /></button></div>
      <label className="m-3 flex items-center gap-2 rounded-xl border border-ink-200 bg-sand-50 px-3 py-2"><Search size={15} className="text-ink-500" /><input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-400" placeholder={t('ui.searchLanguages')} aria-label={t('ui.searchLanguages')} /></label>
      <div className="max-h-72 overflow-y-auto px-2 pb-2">{languages.length ? languages.map((language) => <button type="button" key={language.code} onClick={() => choose(language.code)} className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-leaf-50 focus-ring ${active.code === language.code ? 'bg-leaf-50 text-forest-800' : 'text-ink-700'}`}><span><span className="block text-sm font-semibold">{language.nativeName}</span><span className="block text-xs text-ink-500">{language.englishName}</span></span>{active.code === language.code && <Check size={17} className="text-forest-700" />}</button>) : <p className="px-3 py-6 text-center text-sm text-ink-500">{t('ui.noLanguagesFound')}</p>}</div>
    </div>}
  </div>
}
