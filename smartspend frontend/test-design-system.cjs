const { buildSync } = require('esbuild')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const assert = require('node:assert/strict')

const tokens = readFileSync('src/tokens.css', 'utf8')
const styles = readFileSync('src/styles.css', 'utf8')
const auth = readFileSync('src/components/AuthScreen.css', 'utf8')
for (const color of ['#151719', '#23272c', '#d5f66d', '#f4f5ef']) assert.ok(tokens.includes(color))
assert.ok(styles.includes('@import \'./tokens.css\''))
assert.ok(styles.includes('max-width: none;'))
assert.ok(auth.includes('minmax(480px, 560px)') && auth.includes('clamp(56px, 5vw, 80px)'))
assert.ok(auth.includes('font-weight: 650'))
for (const css of [styles, auth]) {
  assert.ok(!/zoom\s*:|scale\s*\(/.test(css))
  for (const match of css.matchAll(/font-size:\s*(\d+)px/g)) assert.ok(Number(match[1]) >= 14)
}
console.log('PASS approved A tokens, full-width auth and readable production type source checks')

function luminance(hex) {
  const values = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(x => x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4)
  return values.reduce((sum, value, i) => sum + value * [.2126, .7152, .0722][i], 0)
}
for (const [foreground, background] of [['1c2512', 'd5f66d'], ['f4f5ef', '23272c'], ['adb4b8', '23272c'], ['ffb6ad', '392727'], ['f0ce8d', '352c1e'], ['91dfbb', '1b342b']]) {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a)
  assert.ok((values[0] + .05) / (values[1] + .05) >= 4.5)
}
console.log('PASS primary/body/muted/error/warning/success token contrast >= 4.5:1')

const result = buildSync({ entryPoints: [resolve('src/App.jsx')], bundle: true, write: false, metafile: true, platform: 'node', format: 'cjs', packages: 'external', loader: { '.css': 'empty' }, define: { 'import.meta.env': '{}' } })
assert.ok(!Object.keys(result.metafile.inputs).some(path => path.replaceAll('\\', '/').includes('src/previews/')))
buildSync({ entryPoints: [resolve('src/styles.css'), resolve('src/components/AuthScreen.css')], outdir: 'unused-css-check', bundle: true, write: false })
console.log('PASS production dependency graph excludes preview code/CSS; production styles compile')
