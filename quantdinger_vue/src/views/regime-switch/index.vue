<template>
  <div class="regime-switch-page">
    <a-tabs :active-key="activeTabKey" @change="k => activeTabKey = k">
      <!-- 查看 Tab -->
      <a-tab-pane :key="'view'" :tab="$t('regime.viewTab')">
        <div v-if="!multiStrategyEnabled" class="empty-hint">
          <a-alert
            type="info"
            :message="$t('regime.notEnabled')"
            :description="$t('regime.initHint')"
            show-icon
          />
          <a-button type="primary" size="small" @click="activeTabKey = 'config'" style="margin-top: 12px">
            {{ $t('regime.goToConfig') }}
          </a-button>
        </div>
        <template v-else>
          <!-- 顶部摘要 -->
          <div class="summary-section">
            <a-card size="small" class="summary-card">
              <div class="summary-row">
                <div class="summary-item summary-item-regime">
                  <span class="label">{{ $t('regime.currentRegime') }}</span>
                  <div class="regime-tags-wrap">
                    <template v-if="regimePerSymbol && Object.keys(regimePerSymbol).length">
                      <a-tag
                        v-for="(r, sym) in regimePerSymbol"
                        :key="sym"
                        :color="regimeTagColorFor(r)"
                      >
                        {{ sym }}: {{ r }}
                      </a-tag>
                    </template>
                    <a-tag v-else :color="regimeTagColor">{{ summary.regime || '-' }}</a-tag>
                  </div>
                </div>
                <div class="summary-item" v-if="summary.macro">
                  <span class="label">VIX</span>
                  <span>{{ summary.macro.vix != null ? summary.macro.vix.toFixed(2) : '-' }}</span>
                </div>
                <div class="summary-item" v-if="summary.macro && summary.macro.vhsi != null">
                  <span class="label">VHSI</span>
                  <span>{{ summary.macro.vhsi.toFixed(2) }}</span>
                </div>
                <div class="summary-item" v-if="summary.macro">
                  <span class="label">Fear&Greed</span>
                  <span>{{ summary.macro.fear_greed != null ? summary.macro.fear_greed : '-' }}</span>
                </div>
                <div class="summary-item" v-if="!regimePerSymbol || !Object.keys(regimePerSymbol).length">
                  <span class="label">{{ $t('regime.effectiveWeights') }}</span>
                  <span class="weights-text">{{ formatWeights(summary.weights?.effective) }}</span>
                </div>
                <div class="summary-item" v-else>
                  <span class="label">{{ $t('regime.effectiveWeights') }}</span>
                  <span class="weights-text">{{ $t('regime.perSymbolWeights') || '按品种独立' }}</span>
                </div>
                <div class="summary-item" v-if="summary.circuit_breaker?.tripped">
                  <a-tag color="red">{{ $t('regime.circuitBreakerTripped') }}</a-tag>
                  <a-button size="small" type="link" @click="resetCircuitBreaker" :loading="resettingCb">
                    {{ $t('regime.resetCircuitBreaker') }}
                  </a-button>
                </div>
              </div>
            </a-card>
          </div>

          <!-- Per-Market 已配置但尚无数据时的提示 -->
          <a-alert
            v-if="isPerMarketConfigured && (!regimePerSymbol || !Object.keys(regimePerSymbol).length)"
            type="info"
            message="已配置按市场独立 Regime"
            description="港股将用 VHSI、美股用 VIX。等待下次 regime 定时调度运行后，此处将显示各品种的 regime 策略。"
            show-icon
            style="margin-bottom: 16px"
          />

          <!-- Per-Symbol Regime 策略一览：仅在有 regime_per_symbol 时显示 -->
          <a-card
            v-if="regimePerSymbol && Object.keys(regimePerSymbol).length"
            size="small"
            class="per-symbol-regime-card"
            :title="($t('regime.perSymbolRegimeTitle') || '各品种 Regime 策略')"
          >
            <div class="table-desc">按市场选用指标（港股 VHSI、美股 VIX）→ 阈值判定 regime → 应用 regime_to_weights</div>
            <a-table
              class="per-symbol-table"
              :columns="perSymbolRegimeColumns"
              :data-source="perSymbolRegimeTableData"
              :pagination="false"
              size="small"
              bordered
            >
              <template slot="regime" slot-scope="text">
                <a-tag :color="regimeTagColorFor(text)">{{ text }}</a-tag>
              </template>
            </a-table>
          </a-card>

          <!-- 按 Symbol 分组策略与分配资金 -->
          <div class="symbol-groups">
            <a-collapse v-model="expandedSymbols">
              <a-collapse-panel
                v-for="(styleMap, symbol) in symbolStrategies"
                :key="symbol"
                :header="symbolHeader(symbol)"
              >
                <template v-for="(sids, style) in styleMap">
                  <div v-if="sids && sids.length" :key="style" class="style-row">
                    <div class="style-label">
                      <a-tag size="small">{{ style }}</a-tag>
                      <span class="weight-badge">{{ formatWeight(weightsForSymbol(symbol)[style]) }}</span>
                    </div>
                    <div class="strategy-list">
                      <div
                        v-for="sid in sids"
                        :key="sid"
                        class="strategy-item"
                      >
                        <span class="strategy-name">{{ getStrategyName(sid) || `#${sid}` }}</span>
                        <span class="allocated-capital">{{ $t('regime.allocatedCapital') }}: {{ formatAmount(getAllocation(sid)) }}</span>
                        <a-tag v-if="isFrozen(sid)" color="orange" size="small">{{ $t('regime.frozen') }}</a-tag>
                      </div>
                    </div>
                  </div>
                </template>
              </a-collapse-panel>
            </a-collapse>
          </div>
        </template>
      </a-tab-pane>

      <!-- 配置 Tab -->
      <a-tab-pane :key="'config'" :tab="$t('regime.configTab')">
        <div class="config-section">
          <a-spin :spinning="configLoading">
            <!-- 启用开关 -->
            <a-card size="small" class="config-block">
              <a-form layout="inline">
                <a-form-item :label="$t('regime.enableLabel')">
                  <a-switch v-model="formEnabled" @change="onEnableChange" />
                </a-form-item>
              </a-form>
            </a-card>

            <!-- YAML 导入 -->
            <a-card size="small" class="config-block" :title="$t('regime.yamlImport')">
              <a-upload
                :before-upload="beforeYamlUpload"
                :show-upload-list="false"
                accept=".yaml,.yml"
              >
                <a-button><a-icon type="upload" /> {{ $t('regime.selectYaml') }}</a-button>
              </a-upload>
              <div v-if="yamlPreview" class="yaml-preview">
                <pre>{{ yamlPreviewText }}</pre>
                <a-button type="primary" size="small" @click="applyYamlPreview" :loading="configSaving">
                  {{ $t('regime.applyImport') }}
                </a-button>
                <a-button size="small" @click="yamlPreview = null">{{ $t('common.cancel') }}</a-button>
              </div>
            </a-card>

            <!-- 表单配置 -->
            <a-card size="small" class="config-block" :title="$t('regime.formConfig')">
              <!-- Regime 权重 -->
              <div class="form-subsection">
                <h4>{{ $t('regime.regimeWeights') }}</h4>
                <a-table
                  :columns="weightColumns"
                  :data-source="weightTableData"
                  :pagination="false"
                  size="small"
                  bordered
                >
                  <template slot="conservative" slot-scope="text, record">
                    <a-input-number
                      :value="record.conservative"
                      :min="0"
                      :max="1"
                      :step="0.1"
                      style="width: 80px"
                      @change="v => setWeight(record.regime, 'conservative', v)"
                    />
                  </template>
                  <template slot="balanced" slot-scope="text, record">
                    <a-input-number
                      :value="record.balanced"
                      :min="0"
                      :max="1"
                      :step="0.1"
                      style="width: 80px"
                      @change="v => setWeight(record.regime, 'balanced', v)"
                    />
                  </template>
                  <template slot="aggressive" slot-scope="text, record">
                    <a-input-number
                      :value="record.aggressive"
                      :min="0"
                      :max="1"
                      :step="0.1"
                      style="width: 80px"
                      @change="v => setWeight(record.regime, 'aggressive', v)"
                    />
                  </template>
                </a-table>
              </div>

              <!-- 主指标与阈值 -->
              <div class="form-subsection">
                <h4>{{ $t('regime.primaryIndicator') || '主指标' }}</h4>
                <a-form layout="inline" style="margin-bottom: 8px">
                  <a-form-item :label="$t('regime.primaryIndicator') || 'primary_indicator'">
                    <a-select v-model="formRegimeRules.primary_indicator" style="width: 140px">
                      <a-select-option value="vix">VIX（美股）</a-select-option>
                      <a-select-option value="vhsi">VHSI（港股）</a-select-option>
                      <a-select-option value="fear_greed">Fear&Greed</a-select-option>
                      <a-select-option value="auto">auto（港股用 VHSI）</a-select-option>
                      <a-select-option value="custom">custom</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-form>
                <div v-if="formRegimeRules.primary_indicator === 'vix'" class="threshold-row">
                  <span class="threshold-label">VIX:</span>
                  <a-input-number v-model="formRegimeRules.vix_panic" :min="0" :max="100" placeholder="panic" style="width: 70px" />
                  <a-input-number v-model="formRegimeRules.vix_high_vol" :min="0" :max="100" placeholder="high_vol" style="width: 70px" />
                  <a-input-number v-model="formRegimeRules.vix_low_vol" :min="0" :max="100" placeholder="low_vol" style="width: 70px" />
                </div>
                <div v-if="formRegimeRules.primary_indicator === 'vhsi' || formRegimeRules.primary_indicator === 'auto'" class="threshold-row">
                  <span class="threshold-label">VHSI:</span>
                  <a-input-number v-model="formRegimeRules.vhsi_panic" :min="0" :max="100" placeholder="panic" style="width: 70px" />
                  <a-input-number v-model="formRegimeRules.vhsi_high_vol" :min="0" :max="100" placeholder="high_vol" style="width: 70px" />
                  <a-input-number v-model="formRegimeRules.vhsi_low_vol" :min="0" :max="100" placeholder="low_vol" style="width: 70px" />
                </div>
              </div>

              <!-- Symbol 策略绑定 -->
              <div class="form-subsection">
                <h4>{{ $t('regime.symbolStrategies') }}</h4>
                <div class="symbol-add-row">
                  <a-input
                    v-model="newSymbol"
                    :placeholder="$t('regime.addSymbolPlaceholder')"
                    style="width: 120px; margin-right: 8px"
                    @pressEnter="addSymbol"
                  />
                  <a-button type="primary" size="small" @click="addSymbol">{{ $t('common.add') }}</a-button>
                </div>
                <a-collapse v-model="configExpandedSymbols" class="symbol-strategy-collapse">
                  <a-collapse-panel
                    v-for="(styleMap, symbol) in formSymbolStrategies"
                    :key="symbol"
                    :header="symbol"
                  >
                    <div v-for="style in ['conservative', 'balanced', 'aggressive']" :key="style" class="style-strategy-row">
                      <span class="style-label">{{ style }}:</span>
                      <a-select
                        mode="multiple"
                        :value="styleMap[style] || []"
                        :placeholder="$t('regime.selectStrategies')"
                        style="min-width: 300px"
                        @change="v => setSymbolStrategy(symbol, style, v)"
                      >
                        <a-select-option v-for="s in strategies" :key="s.id" :value="s.id">
                          {{ s.strategy_name || s.displayInfo?.strategyName || `#${s.id}` }}
                        </a-select-option>
                      </a-select>
                    </div>
                    <a-button type="link" size="small" danger @click="removeSymbol(symbol)" class="remove-symbol-btn">
                      {{ $t('regime.removeSymbol') }}
                    </a-button>
                  </a-collapse-panel>
                </a-collapse>
              </div>

              <a-button type="primary" @click="saveConfig" :loading="configSaving" class="save-btn">
                {{ $t('common.save') }}
              </a-button>
            </a-card>
          </a-spin>
        </div>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script>
import { getSummary, getAllocation, getConfig, putConfig, parseYamlConfig, resetCircuitBreaker } from '@/api/multiStrategy'
import { getStrategyList } from '@/api/strategy'

const DEFAULT_REGIME_TO_WEIGHTS = {
  panic: { conservative: 0.80, balanced: 0.20, aggressive: 0 },
  high_vol: { conservative: 0.50, balanced: 0.40, aggressive: 0.10 },
  normal: { conservative: 0.20, balanced: 0.60, aggressive: 0.20 },
  low_vol: { conservative: 0.10, balanced: 0.30, aggressive: 0.60 }
}
const DEFAULT_REGIME_RULES = {
  primary_indicator: 'vix',
  vix_panic: 30,
  vix_high_vol: 25,
  vix_low_vol: 15,
  vhsi_panic: 30,
  vhsi_high_vol: 25,
  vhsi_low_vol: 15,
  indicator_per_market: {
    HShare: 'vhsi',
    default: 'vix'
  }
}

export default {
  name: 'RegimeSwitch',
  data () {
    return {
      loading: false,
      multiStrategyEnabled: false,
      summary: {
        regime: '',
        macro: {},
        weights: { effective: {}, target: {} },
        allocation: {},
        circuit_breaker: {}
      },
      allocationData: { allocation: {}, frozen: {} },
      configData: { symbol_strategies: {}, multi_strategy: {}, regime_rules: {} },
      strategies: [],
      expandedSymbols: [],
      resettingCb: false,

      // 配置 Tab
      formEnabled: false,
      formRegimeToWeights: { ...DEFAULT_REGIME_TO_WEIGHTS },
      formRegimeRules: { ...DEFAULT_REGIME_RULES },
      formSymbolStrategies: {},
      newSymbol: '',
      configExpandedSymbols: [],
      yamlPreview: null,
      configLoading: false,
      configSaving: false,
      activeTabKey: 'view'
    }
  },
  computed: {
    symbolStrategies () {
      return this.configData.symbol_strategies || {}
    },
    weightsEffective () {
      return this.summary.weights?.effective || {}
    },
    regimePerSymbol () {
      return this.summary.regime_per_symbol || {}
    },
    weightsPerSymbol () {
      return this.summary.weights_per_symbol || {}
    },
    isPerMarketConfigured () {
      const rr = (this.configData.regime_rules || {})
      const indicator = (rr.primary_indicator || '').toString().toLowerCase()
      const perMarket = rr.indicator_per_market || {}
      return indicator === 'auto' && Object.keys(perMarket).length > 0
    },
    regimeTagColor () {
      const m = { panic: 'red', high_vol: 'orange', normal: 'green', low_vol: 'blue' }
      return m[this.summary.regime] || 'default'
    },
    weightTableData () {
      const regimes = ['panic', 'high_vol', 'normal', 'low_vol']
      const w = this.formRegimeToWeights
      return regimes.map(regime => ({
        key: regime,
        regime,
        conservative: w[regime]?.conservative ?? 0,
        balanced: w[regime]?.balanced ?? 0,
        aggressive: w[regime]?.aggressive ?? 0
      }))
    },
    weightColumns () {
      return [
        { title: 'Regime', dataIndex: 'regime', key: 'regime', width: 100 },
        { title: 'Conservative', dataIndex: 'conservative', key: 'conservative', scopedSlots: { customRender: 'conservative' } },
        { title: 'Balanced', dataIndex: 'balanced', key: 'balanced', scopedSlots: { customRender: 'balanced' } },
        { title: 'Aggressive', dataIndex: 'aggressive', key: 'aggressive', scopedSlots: { customRender: 'aggressive' } }
      ]
    },
    yamlPreviewText () {
      if (!this.yamlPreview) return ''
      return JSON.stringify(this.yamlPreview, null, 2)
    },
    perSymbolRegimeColumns () {
      return [
        { title: '品种', dataIndex: 'symbol', key: 'symbol', width: 100 },
        { title: '指标依据', dataIndex: 'indicatorBasis', key: 'indicatorBasis', width: 140 },
        { title: 'Regime', dataIndex: 'regime', key: 'regime', width: 90, scopedSlots: { customRender: 'regime' } },
        { title: '生效权重', dataIndex: 'weights', key: 'weights' }
      ]
    },
    perSymbolRegimeTableData () {
      const rps = this.regimePerSymbol || {}
      const wps = this.weightsPerSymbol || {}
      const ips = this.summary.indicator_per_symbol || {}
      const macro = this.summary.macro || {}
      return Object.keys(rps).map(sym => {
        const ind = ips[sym] || 'vix'
        const val = macro[ind] != null ? Number(macro[ind]).toFixed(1) : '-'
        const indLabel = ind.toUpperCase()
        const regime = rps[sym]
        return {
          key: sym,
          symbol: sym,
          indicatorBasis: `${indLabel} ${val} → ${regime}`,
          regime,
          weights: this.formatWeights(wps[sym] || {})
        }
      })
    }
  },
  watch: {
    'configData.multi_strategy.enabled' (val) {
      this.formEnabled = !!val
    },
    activeTabKey (key) {
      if (key === 'config') this.loadConfigToForm()
    }
  },
  mounted () {
    this.loadData()
  },
  methods: {
    async loadData () {
      this.loading = true
      try {
        const results = await Promise.allSettled([
          getSummary(),
          getAllocation(),
          getConfig(),
          getStrategyList()
        ])
        const summaryRes = results[0].status === 'fulfilled' ? results[0].value : null
        const allocRes = results[1].status === 'fulfilled' ? results[1].value : null
        const configRes = results[2].status === 'fulfilled' ? results[2].value : null
        const strategiesRes = results[3].status === 'fulfilled' ? results[3].value : null

        // request 拦截器返回 response.data，故 res 即 {code, msg, data}
        const summaryOk = summaryRes?.code === 1 && summaryRes?.data
        const summaryMsg = summaryRes?.msg
        const configOk = configRes?.code === 1 && configRes?.data
        const configData = configOk ? configRes.data : null

        // 以 config 为首要依据：先处理 config，enabled 状态以 config 为准
        if (configOk && configData) {
          this.configData = configData
          this.expandedSymbols = Object.keys(this.configData.symbol_strategies || {})
          if (this.activeTabKey === 'config') this.loadConfigToForm()
          const enabled = (this.configData.multi_strategy || {}).enabled
          this.multiStrategyEnabled = enabled === true || enabled === 'true' || enabled === 1
        }

        // summary 成功时也设为启用；summary 失败不影响已由 config 确定的启用状态
        if (summaryOk) {
          this.summary = summaryRes.data
          this.multiStrategyEnabled = true
        } else if (summaryMsg === 'multi-strategy not enabled' && !configOk) {
          this.multiStrategyEnabled = false
        }

        if (allocRes?.code === 1 && allocRes?.data) {
          this.allocationData = allocRes.data
        }

        if (strategiesRes?.code === 1 && strategiesRes?.data?.strategies) {
          this.strategies = strategiesRes.data.strategies
        }
      } catch (e) {
        this.multiStrategyEnabled = false
      } finally {
        this.loading = false
      }
    },
    getStrategyName (sid) {
      const s = this.strategies.find(x => x.id === sid || x.id === parseInt(sid))
      return s ? (s.strategy_name || s.displayInfo?.strategyName) : null
    },
    weightsForSymbol (symbol) {
      const per = this.weightsPerSymbol[symbol]
      if (per && Object.keys(per).length) return per
      return this.weightsEffective
    },
    regimeTagColorFor (regime) {
      const m = { panic: 'red', high_vol: 'orange', normal: 'green', low_vol: 'blue' }
      return m[regime] || 'default'
    },
    symbolHeader (symbol) {
      const r = this.regimePerSymbol[symbol]
      if (r) return `${symbol} (${r})`
      return symbol
    },
    getAllocation (sid) {
      const id = typeof sid === 'number' ? sid : parseInt(sid)
      return this.allocationData.allocation?.[id] ?? this.summary.allocation?.[id] ?? 0
    },
    isFrozen (sid) {
      const id = typeof sid === 'number' ? sid : parseInt(sid)
      return !!this.allocationData.frozen?.[id]
    },
    formatWeights (w) {
      if (!w || typeof w !== 'object') return '-'
      const parts = Object.entries(w).filter(([, v]) => v > 0).map(([k, v]) => `${k}:${(v * 100).toFixed(0)}%`)
      return parts.length ? parts.join(' ') : '-'
    },
    formatWeight (v) {
      if (v == null || v === undefined) return '-'
      return `${(Number(v) * 100).toFixed(0)}%`
    },
    formatAmount (v) {
      if (v == null || v === undefined) return '-'
      const n = Number(v)
      if (isNaN(n)) return '-'
      return n >= 10000 ? `${(n / 10000).toFixed(1)}w` : n.toLocaleString(undefined, { maximumFractionDigits: 0 })
    },
    async resetCircuitBreaker () {
      this.resettingCb = true
      try {
        await resetCircuitBreaker()
        this.$message.success(this.$t('regime.resetSuccess'))
        this.loadData()
      } catch (e) {
        this.$message.error(e?.message || 'Failed')
      } finally {
        this.resettingCb = false
      }
    },
    loadConfigToForm () {
      const cfg = this.configData
      const ms = cfg.multi_strategy || {}
      const rr = cfg.regime_rules || {}
      const r2w = ms.regime_to_weights || cfg.regime_to_weights
      this.formEnabled = !!ms.enabled
      this.formRegimeToWeights = r2w && Object.keys(r2w).length
        ? JSON.parse(JSON.stringify(r2w))
        : { ...DEFAULT_REGIME_TO_WEIGHTS }
      this.formRegimeRules = {
        primary_indicator: rr.primary_indicator ?? DEFAULT_REGIME_RULES.primary_indicator,
        vix_panic: rr.vix_panic ?? DEFAULT_REGIME_RULES.vix_panic,
        vix_high_vol: rr.vix_high_vol ?? DEFAULT_REGIME_RULES.vix_high_vol,
        vix_low_vol: rr.vix_low_vol ?? DEFAULT_REGIME_RULES.vix_low_vol,
        vhsi_panic: rr.vhsi_panic ?? DEFAULT_REGIME_RULES.vhsi_panic,
        vhsi_high_vol: rr.vhsi_high_vol ?? DEFAULT_REGIME_RULES.vhsi_high_vol,
        vhsi_low_vol: rr.vhsi_low_vol ?? DEFAULT_REGIME_RULES.vhsi_low_vol,
        indicator_per_market: rr.indicator_per_market ?? DEFAULT_REGIME_RULES.indicator_per_market
      }
      const ss = cfg.symbol_strategies || {}
      this.formSymbolStrategies = JSON.parse(JSON.stringify(ss))
      this.configExpandedSymbols = Object.keys(this.formSymbolStrategies)
    },
    beforeYamlUpload (file) {
      this.configLoading = true
      parseYamlConfig(file)
        .then(res => {
          if (res?.code === 1 && res?.data) {
            this.yamlPreview = res.data
          } else {
            this.$message.error(res?.msg || 'Parse failed')
          }
        })
        .catch(e => {
          this.$message.error(e?.message || 'Parse failed')
        })
        .finally(() => {
          this.configLoading = false
        })
      return false
    },
    async applyYamlPreview () {
      if (!this.yamlPreview) return
      const p = this.yamlPreview
      this.formRegimeToWeights = (p.regime_to_weights && Object.keys(p.regime_to_weights).length)
        ? JSON.parse(JSON.stringify(p.regime_to_weights))
        : { ...DEFAULT_REGIME_TO_WEIGHTS }
      if (p.regime_rules) {
        this.formRegimeRules = {
          primary_indicator: p.regime_rules.primary_indicator ?? DEFAULT_REGIME_RULES.primary_indicator,
          vix_panic: p.regime_rules.vix_panic ?? DEFAULT_REGIME_RULES.vix_panic,
          vix_high_vol: p.regime_rules.vix_high_vol ?? DEFAULT_REGIME_RULES.vix_high_vol,
          vix_low_vol: p.regime_rules.vix_low_vol ?? DEFAULT_REGIME_RULES.vix_low_vol,
          vhsi_panic: p.regime_rules.vhsi_panic ?? DEFAULT_REGIME_RULES.vhsi_panic,
          vhsi_high_vol: p.regime_rules.vhsi_high_vol ?? DEFAULT_REGIME_RULES.vhsi_high_vol,
          vhsi_low_vol: p.regime_rules.vhsi_low_vol ?? DEFAULT_REGIME_RULES.vhsi_low_vol,
          indicator_per_market: p.regime_rules.indicator_per_market ?? DEFAULT_REGIME_RULES.indicator_per_market
        }
      }
      if (p.symbol_strategies && Object.keys(p.symbol_strategies).length) {
        this.formSymbolStrategies = JSON.parse(JSON.stringify(p.symbol_strategies))
      }
      this.yamlPreview = null
      await this.saveConfig()
    },
    setWeight (regime, style, v) {
      this.$set(this.formRegimeToWeights, regime, this.formRegimeToWeights[regime] || {})
      this.$set(this.formRegimeToWeights[regime], style, v == null ? 0 : Number(v))
    },
    addSymbol () {
      const s = (this.newSymbol || '').trim().toUpperCase()
      if (!s) return
      if (this.formSymbolStrategies[s]) {
        this.$message.warning(this.$t('regime.symbolExists') || `Symbol ${s} already exists`)
        return
      }
      this.$set(this.formSymbolStrategies, s, { conservative: [], balanced: [], aggressive: [] })
      this.configExpandedSymbols = [...new Set([...this.configExpandedSymbols, s])]
      this.newSymbol = ''
    },
    setSymbolStrategy (symbol, style, val) {
      if (!this.formSymbolStrategies[symbol]) return
      this.$set(this.formSymbolStrategies[symbol], style, Array.isArray(val) ? val : [])
    },
    removeSymbol (symbol) {
      this.$delete(this.formSymbolStrategies, symbol)
      this.configExpandedSymbols = this.configExpandedSymbols.filter(x => x !== symbol)
    },
    async saveConfig () {
      this.configSaving = true
      try {
        const body = {
          symbol_strategies: this.formSymbolStrategies,
          regime_to_weights: this.formRegimeToWeights,
          regime_rules: this.formRegimeRules,
          multi_strategy: {
            ...(this.configData.multi_strategy || {}),
            enabled: this.formEnabled,
            regime_to_weights: this.formRegimeToWeights
          }
        }
        const res = await putConfig(body)
        if (res?.code === 1) {
          this.$message.success(this.$t('regime.saveSuccess') || this.$t('save.ok'))
          this.configData = { ...this.configData, ...body }
          this.multiStrategyEnabled = this.formEnabled
          this.loadData()
        } else {
          this.$message.error(res?.msg || 'Save failed')
        }
      } catch (e) {
        this.$message.error(e?.message || 'Save failed')
      } finally {
        this.configSaving = false
      }
    },
    onEnableChange (checked) {
      this.formEnabled = !!checked
      this.saveConfig()
    }
  }
}
</script>

<style lang="less" scoped>
.regime-switch-page {
  padding: 16px;
}
.empty-hint, .config-placeholder {
  padding: 24px;
}
.summary-section {
  margin-bottom: 16px;
}
.per-symbol-regime-card {
  margin-bottom: 16px;
}
.table-desc {
  font-size: 12px;
  color: #8c8c8c;
  margin-bottom: 12px;
}
.summary-card .summary-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  max-width: 100%;
}
.summary-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  .label { color: #8c8c8c; font-size: 12px; flex-shrink: 0; }
  .weights-text { font-size: 12px; }
}
.summary-item-regime {
  flex: 1 1 auto;
  min-width: 0;
  max-width: 100%;
}
.regime-tags-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
  max-width: 100%;
}
.symbol-groups {
  margin-top: 16px;
}
.style-row {
  margin-bottom: 12px;
  padding: 8px;
  background: #fafafa;
  border-radius: 4px;
}
.style-label {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  .weight-badge { font-size: 12px; color: #1890ff; }
}
.strategy-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.strategy-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  .strategy-name { flex: 1; }
  .allocated-capital { color: #52c41a; font-weight: 500; }
}

.config-section { padding: 16px 0; }
.config-block { margin-bottom: 16px; }
.form-subsection {
  margin-bottom: 20px;
  h4 { margin-bottom: 12px; font-size: 14px; }
}
.threshold-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  .threshold-label { min-width: 50px; font-size: 13px; }
}
.style-strategy-row {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  .style-label { min-width: 100px; }
}
.remove-symbol-btn { margin-top: 8px; }
.symbol-add-row { margin-bottom: 12px; }
.save-btn { margin-top: 16px; }
.yaml-preview {
  margin-top: 12px;
  pre { font-size: 12px; max-height: 200px; overflow: auto; background: #f5f5f5; padding: 12px; border-radius: 4px; }
}
</style>
