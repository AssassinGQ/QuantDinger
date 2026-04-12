/**
 * FRNT-02 / TEST-02: trading-assistant wizard — Forex + IBKR paths (Jest, no browser).
 * @jest-environment jsdom
 */
jest.mock('@/api/strategy', () => ({
  getStrategyList: jest.fn(() => Promise.resolve({ code: 1, data: { strategies: [] } })),
  startStrategy: jest.fn(),
  stopStrategy: jest.fn(),
  deleteStrategy: jest.fn(),
  updateStrategy: jest.fn(),
  createStrategy: jest.fn(),
  testExchangeConnection: jest.fn(),
  getStrategyEquityCurve: jest.fn(),
  batchCreateStrategies: jest.fn(),
  batchStartStrategies: jest.fn(),
  batchStopStrategies: jest.fn(),
  batchDeleteStrategies: jest.fn(),
  forceRebalanceStrategy: jest.fn(),
  forceCloseAllStrategy: jest.fn()
}))

jest.mock('@/api/market', () => ({
  getWatchlist: jest.fn(() => Promise.resolve({ code: 1, data: [] })),
  addWatchlist: jest.fn(),
  searchSymbols: jest.fn(),
  getHotSymbols: jest.fn()
}))

jest.mock('@/api/credentials', () => ({
  listExchangeCredentials: jest.fn(() => Promise.resolve({ code: 1, data: [] })),
  getExchangeCredential: jest.fn(),
  createExchangeCredential: jest.fn()
}))

jest.mock('@/api/user', () => ({
  getNotificationSettings: jest.fn(() => Promise.resolve({ code: 1, data: {} }))
}))

jest.mock('@/utils/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn()
  }
}))

import { createLocalVue, shallowMount } from '@vue/test-utils'
import Vuex from 'vuex'
import TradingAssistant from '@/views/trading-assistant/index.vue'

function createFormMock () {
  return {
    getFieldDecorator: () => () => {},
    getFieldValue: () => undefined,
    getFieldsValue: () => ({}),
    setFieldsValue: jest.fn(),
    validateFields: (cb) => cb && cb(null, {})
  }
}

describe('FRNT-02: trading-assistant wizard Forex / IBKR (TEST-02)', () => {
  let localVue
  let store

  beforeEach(() => {
    localVue = createLocalVue()
    localVue.use(Vuex)
    store = new Vuex.Store({
      state: {
        app: {
          layout: 'sidemenu',
          theme: 'light',
          color: '#1890ff',
          weak: false,
          fixedHeader: true,
          fixedSidebar: true,
          contentWidth: 'Fluid',
          autoHideHeader: false,
          isMobile: false,
          sideCollapsed: false,
          multiTab: false
        }
      }
    })
  })

  it('shallow-mounts TradingAssistant; HTML reflects ibkr-paper when Forex + IBKR paper broker', async () => {
    const wrapper = shallowMount(TradingAssistant, {
      localVue,
      store,
      sync: false,
      mocks: {
        $form: { createForm: () => createFormMock() },
        $t: (key) => key,
        $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn(), info: jest.fn() }
      },
      stubs: {
        'a-row': true,
        'a-col': true,
        'a-card': true,
        'a-button': true,
        'a-icon': true,
        'a-spin': true,
        'a-empty': true,
        'a-radio-group': true,
        'a-radio-button': true,
        'a-dropdown': true,
        'a-menu': true,
        'a-menu-item': true,
        'a-menu-divider': true,
        'a-tag': true,
        'a-modal': true,
        'a-form': true,
        'a-form-item': true,
        'a-input': true,
        'a-select': true,
        'a-divider': true,
        'a-switch': true,
        'a-tooltip': true,
        'a-alert': true,
        'a-tabs': true,
        'a-tab-pane': true,
        'a-table': true,
        'a-collapse': true,
        'a-collapse-panel': true,
        'a-slider': true,
        'a-input-number': true,
        'a-checkbox': true,
        'a-checkbox-group': true,
        'a-textarea': true,
        'a-list': true,
        'a-list-item': true,
        'a-radio': true,
        'a-select-option': { template: '<option><slot /></option>', props: ['value'] },
        'router-link': true
      }
    })

    await wrapper.vm.$nextTick()
    // Step 2 + live mode: template shows Forex broker select (forexBrokerOptions includes ibkr-paper).
    wrapper.setData({
      showFormModal: true,
      currentStep: 2,
      selectedMarketCategory: 'Forex',
      currentBrokerId: 'ibkr-paper',
      executionModeUi: 'live'
    })
    await wrapper.vm.$nextTick()

    const html = wrapper.html()
    expect(html).toMatch(/ibkr-paper|IBKR Paper/)
  })

  it('forexBrokerOptions includes ibkr-paper; isForexMarket and isForexIBKR when Forex + IBKR', async () => {
    const wrapper = shallowMount(TradingAssistant, {
      localVue,
      store,
      sync: false,
      mocks: {
        $form: { createForm: () => createFormMock() },
        $t: (key) => key,
        $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn(), info: jest.fn() }
      },
      stubs: {
        'a-row': true,
        'a-col': true,
        'a-card': true,
        'a-button': true,
        'a-icon': true,
        'a-spin': true,
        'a-empty': true,
        'a-radio-group': true,
        'a-radio-button': true,
        'a-dropdown': true,
        'a-menu': true,
        'a-menu-item': true,
        'a-menu-divider': true,
        'a-tag': true,
        'a-modal': true,
        'a-form': true,
        'a-form-item': true,
        'a-input': true,
        'a-select': true,
        'a-select-option': true,
        'a-divider': true,
        'a-switch': true,
        'a-tooltip': true,
        'a-alert': true,
        'a-tabs': true,
        'a-tab-pane': true,
        'a-table': true,
        'a-collapse': true,
        'a-collapse-panel': true,
        'a-slider': true,
        'a-input-number': true,
        'a-checkbox': true,
        'a-checkbox-group': true,
        'a-textarea': true,
        'a-list': true,
        'a-list-item': true,
        'router-link': true
      }
    })

    await wrapper.vm.$nextTick()
    wrapper.setData({
      selectedMarketCategory: 'Forex',
      currentBrokerId: 'ibkr-paper'
    })
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.isForexMarket).toBe(true)
    expect(wrapper.vm.isForexIBKR).toBe(true)
    const values = wrapper.vm.forexBrokerOptions.map((o) => o.value)
    expect(values).toContain('ibkr-paper')
    const names = wrapper.vm.forexBrokerOptions.map((o) => o.name || o.displayName)
    expect(names.some((n) => String(n).includes('IBKR'))).toBe(true)
  })
})
