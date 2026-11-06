import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'

const localeDir = join(process.cwd(), 'src', 'i18n', 'locales')
const flatten = (value, prefix = '') => Object.entries(value).reduce((keys, [key, child]) => {
  const path = prefix ? `${prefix}.${key}` : key
  if (child && typeof child === 'object' && !Array.isArray(child)) Object.assign(keys, flatten(child, path))
  else keys[path] = child
  return keys
}, {})

const english = flatten(JSON.parse(await readFile(join(localeDir, 'en.json'), 'utf8')))
const files = (await readdir(localeDir)).filter((file) => file.endsWith('.json')).sort()
let incomplete = false

for (const file of files) {
  const keys = flatten(JSON.parse(await readFile(join(localeDir, file), 'utf8')))
  const missing = Object.keys(english).filter((key) => !(key in keys))
  const localized = Object.keys(english).length - missing.length
  console.log(`${file}: ${localized}/${Object.keys(english).length} localized; ${missing.length} uses English fallback`)
  if (missing.length) {
    incomplete = true
    console.log(`  Review keys: ${missing.join(', ')}`)
  }
}

if (incomplete) console.log('\nAll keys are available at runtime through English fallback. Complete the listed regional copy before production translation sign-off.')
