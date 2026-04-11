const fs = require('fs')
const path = require('path')

describe('FRNT-01: Forex broker options include IBKR paper/live', () => {
  it('reads index.vue and asserts FOREX_BROKER_OPTIONS shape', () => {
    const vuePath = path.join(__dirname, '../../src/views/trading-assistant/index.vue')
    const content = fs.readFileSync(vuePath, 'utf8')

    expect(content).toMatch(/value:\s*'ibkr-paper'/)
    expect(content).toMatch(/value:\s*'ibkr-live'/)
    expect(content).toContain('isForexMarket')
    expect(content).not.toContain('isMT5Market')
  })
})
