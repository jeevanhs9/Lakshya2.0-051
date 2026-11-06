import { readdir, readFile } from 'node:fs/promises'
import { join, relative } from 'node:path'

const sourceRoot = join(process.cwd(), 'src')
const excluded = new Set(['data', 'assets', 'i18n'])
const isSourceFile = (name) => /\.(jsx|js)$/.test(name)
const ignored = /^(className|key|id|type|role|href|to|value|size|strokeWidth|viewBox|dataKey)$/

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const paths = []
  for (const entry of entries) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) {
      if (!excluded.has(entry.name)) paths.push(...await walk(path))
    } else if (isSourceFile(entry.name)) paths.push(path)
  }
  return paths
}

const files = await walk(sourceRoot)
const findings = []
for (const file of files) {
  const content = await readFile(file, 'utf8')
  const lines = content.split(/\r?\n/)
  lines.forEach((line, index) => {
    if (line.includes('t(') || line.includes('i18n') || line.includes('// i18n-ignore')) return
    const textNode = line.match(/>\s*([A-Z][^<{]{2,})\s*</)
    const attribute = line.match(/\b(placeholder|aria-label|title)=['"]([^'"]{3,})['"]/)
    if (textNode || (attribute && !ignored.test(attribute[1]))) {
      const text = textNode ? textNode[1] : attribute?.[2] ?? ''
      findings.push({ file: relative(process.cwd(), file), line: index + 1, text: text.trim() })
    }
  })
}

const byFile = Map.groupBy(findings, ({ file }) => file)
console.log(`i18n audit: ${findings.length} candidate hardcoded UI strings in ${byFile.size} files.`)
for (const [file, items] of byFile) console.log(`${file}: ${items.length}`)
console.log('\nUse explicit t("namespace.key") calls for UI copy. Dynamic database/API values are intentionally excluded from this audit.')
