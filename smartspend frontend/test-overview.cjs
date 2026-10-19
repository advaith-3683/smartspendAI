// Financial/presentation regression coverage; these are not viewport tests.
const { buildSync } = require('esbuild')
const { resolve } = require('node:path')
const Module = require('node:module')
const assert = require('node:assert/strict')
const React = require('react')
const { renderToString } = require('react-dom/server')
const bundle = buildSync({ entryPoints: [resolve('src/components/Overview.jsx')], bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external' }).outputFiles[0].text
const mod = new Module(resolve('overview.generated.cjs'), module)
mod.filename = resolve('overview.generated.cjs'); mod.paths = module.paths; mod._compile(bundle, mod.filename)
const base = { user: { name: 'Isolated Fixture', monthly_income: 1000.15 }, pace: [{ category: 'Food', projected_spend: 10.1 }],
  transactions: [{ id: 1, amount: .1, category: 'Food', date: '2020-01-01', source: 'manual' },
    { id: 2, amount: .2, category: 'Food', date: '2020-01-02', source: 'manual' },
    { id: 3, amount: 1.25, category: 'Other', date: '2020-01-03', source: 'manual' },
    { id: 4, amount: 999.99, category: 'Scheduled', date: '2200-01-01', source: 'manual' }],
  bills: [], loaded: true, loading: false, error: '', onSelect: () => {}, onAdd: () => {} }
const render = props => renderToString(React.createElement(mod.exports.default, { ...base, ...props }))
const html = render({})
const metrics = html.slice(html.indexOf('overview-metrics'), html.indexOf('panel-footnote'))
for (const value of ['1,000.15', '1.55', '998.60', '11.35']) assert.ok(metrics.includes(value), `Missing expected financial value ${value}`)
assert.ok(!metrics.includes('999.99'))
assert.ok(html.includes('Scheduled'), 'Future entries stay visible in the ledger')
console.log('PASS dashboard cents, remaining income, unbudgeted projections and scheduled-entry exclusion')
assert.ok(html.indexOf('Financial overview') < html.indexOf('Spending insights'))
assert.ok(html.indexOf('Spending insights') < html.indexOf('Recent transactions'))
assert.ok(html.includes('data-label="Amount"') && html.includes('responsive-table'))
console.log('PASS dashboard content hierarchy and mobile table labels (no viewport assertion)')
const failed = render({ loaded: false, error: 'Network unavailable' })
assert.ok(failed.includes('financial overview is unavailable'))
assert.ok(!failed.includes('overview-metrics'))
console.log('PASS dashboard failure never replaces missing data with financial totals')
const empty = render({ transactions: [], pace: [] })
assert.ok(empty.includes('A clear picture starts here') && empty.includes('Your ledger is ready'))
assert.ok(!empty.includes('undefined') && !empty.includes('NaN'))
console.log('PASS new-account empty state has real next actions and no invented statistics')
const loading = render({ loaded: false, loading: true })
assert.ok(loading.includes('role="status"') && loading.includes('summary-skeleton'))
assert.ok(!loading.includes('overview-metrics'))
console.log('PASS loading state presents placeholders rather than fake balances')
