import test from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import { documentFrameHtml } from './documentFrame.mjs'

function fixture(href, options = {}) {
  let handler, prevented = false, scrolled = false
  const html = documentFrameHtml('<html><body><section id="section-3"></section></body></html>')
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  const target = { scrollIntoView() { scrolled = true } }
  vm.runInNewContext(script, { document: {
    addEventListener(type, callback) { assert.equal(type, 'click'); handler = callback },
    getElementById(id) { return id === 'section-3' ? target : null },
    documentElement: target,
  } })
  handler({ button: 0, target: { closest() { return {
    getAttribute() { return href }, hasAttribute() { return false },
  } } }, preventDefault() { prevented = true }, ...options })
  return { prevented, scrolled }
}

test('section and encoded fragment links scroll without navigating srcdoc', () => {
  assert.deepEqual(fixture('#section-3'), { prevented: true, scrolled: true })
  assert.deepEqual(fixture('#section%2D3'), { prevented: true, scrolled: true })
  assert.deepEqual(fixture('#'), { prevented: true, scrolled: true })
})
test('missing or malformed fragments cannot navigate to a blank shell', () => {
  assert.deepEqual(fixture('#missing'), { prevented: true, scrolled: false })
  assert.deepEqual(fixture('#%'), { prevented: true, scrolled: false })
})
test('cross-document and external navigation remain unchanged', () => {
  assert.deepEqual(fixture('/docs/home'), { prevented: false, scrolled: false })
  assert.deepEqual(fixture('https://example.com'), { prevented: false, scrolled: false })
  assert.deepEqual(fixture('#section-3', { ctrlKey: true }), { prevented: false, scrolled: false })
})
