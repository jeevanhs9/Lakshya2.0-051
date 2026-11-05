import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { PHRASE_KEYS } from './phraseMap'
import { languageByCode } from './languages'

const ATTRIBUTE_NAMES = ['aria-label', 'placeholder', 'title']

function translateValue(value, t) {
  const trimmed = value?.trim()
  const key = PHRASE_KEYS[trimmed]
  if (!key) return value
  const leading = value.slice(0, value.indexOf(trimmed))
  const trailing = value.slice(value.indexOf(trimmed) + trimmed.length)
  return `${leading}${t(`ui.${key}`, { defaultValue: trimmed })}${trailing}`
}

export default function LocalizedUi({ children }) {
  const { i18n, t } = useTranslation()
  const originals = useRef(new WeakMap())

  useEffect(() => {
    const root = document.getElementById('root')
    if (!root) return undefined
    const language = languageByCode(i18n.resolvedLanguage || i18n.language)
    document.documentElement.lang = language.code
    document.documentElement.dir = language.dir
    document.title = language.code === 'en' ? 'FarmLink AI' : `${t('ui.appName')} · FarmLink AI`

    const localizeElement = (element) => {
      ATTRIBUTE_NAMES.forEach((attribute) => {
        const original = element.dataset?.[`i18n${attribute.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())}`]
          || element.getAttribute?.(attribute)
        if (!original) return
        if (element.dataset) element.dataset[`i18n${attribute.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())}`] = original
        const translated = translateValue(original, t)
        if (translated !== original || language.code === 'en') element.setAttribute(attribute, translated)
      })
    }
    const localizeTree = (node) => {
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT)
      const textNodes = []
      while (walker.nextNode()) textNodes.push(walker.currentNode)
      textNodes.forEach((textNode) => {
        const parent = textNode.parentElement
        if (!parent || ['SCRIPT', 'STYLE', 'CODE'].includes(parent.tagName)) return
        const original = originals.current.get(textNode) || textNode.nodeValue
        originals.current.set(textNode, original)
        const translated = translateValue(original, t)
        if (translated !== textNode.nodeValue) textNode.nodeValue = translated
      })
      if (node.nodeType === Node.ELEMENT_NODE) localizeElement(node)
      node.querySelectorAll?.('*').forEach(localizeElement)
    }
    localizeTree(root)
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE || node.nodeType === Node.ELEMENT_NODE) localizeTree(node)
        })
      })
    })
    observer.observe(root, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [i18n.language, i18n.resolvedLanguage, t])

  return children
}
