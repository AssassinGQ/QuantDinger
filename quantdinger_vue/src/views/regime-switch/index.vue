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
                <div class="summary-item">
                  <span class="label">{{ $t('regime.currentRegime') }}</span>
                  <a-tag :color="regimeTagColor">{{ summary.regime || '-' }}</a-tag>
                </div>
                <div class="summary-item" v-if="summary.macro">
                  <span class="label">VIX</span>
                  <span>{{ summary.macro.vix != null ? summary.macro.vix.toFixed(2) : '-' }}</span>
                </div>
                <div class="summary-item" v-if="summary.macro">
                  <span class="label">Fear&Greed</span>
                  <span>{{ summary.macro.fear_greed != null ? summary.macro.fear_greed : '-' }}</span>
                </div>
                <div class="summary-item">
                  <span class="label">{{ $t('regime.effectiveWeights') }}</span>
                  <span class="weights-text">{{ formatWeights(summary.weights?.effective) }}</span>
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

          <!-- 按 Symbol 分组策略与分配资金 -->
          <div class="symbol-groups">
            <a-collapse v-model="expandedSymbols">
              <a-collapse-panel
                v-for="(styleMap, symbol) in symbolStrategies"
                :key="symbol"
                :header="symbol"
              >
                <template v-for="(sids, style) in styleMap">
                  <div v-if="sids && sids.length" :key="style" class="style-row">
                    <div class="style-label">
                      <a-tag size="small">{{ style }}</a-tag>
                      <span class="weight-badge">{{ formatWeight(weightsEffective[style]) }}</span>
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

              <!-- VIX 阈值 -->
              <div class="form-subsection">
                <h4>{{ $t('regime.vixThresholds') }}</h4>
                <a-form layout="inline">
                  <a-form-item label="vix_panic">
                    <a-input-number v-model="formRegimeRules.vix_panic" :min="0" :max="100" style="width: 80px" />
                  </a-form-item>
                  <a-form-item label="vix_high_vol">
                    <a-input-number v-model="formRegimeRules.vix_high_vol" :min="0" :max="100" style="width: 80px" />
                  </a-form-item>
                  <a-form-item label="vix_low_vol">
                    <a-input-number v-model="formRegimeRules.vix_low_vol" :min="0" :max="100" style="width: 80px" />
                  </a-form-item>
                </a-form>
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
const DEFAULT_REGIME_RULES = { vix_panic: 30, vix_high_vol: 25, vix_low_vol: 15 }

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
        const [summaryRes, allocRes, configRes, strategiesRes] = await Promise.all([
          getSummary(),
          getAllocation(),
          getConfig(),
          getStrategyList()
        ])

        if (summaryRes?.data?.code === 1 && summaryRes?.data?.data) {
          this.summary = summaryRes.data.data
          this.multiStrategyEnabled = true
        } else if (summaryRes?.data?.msg === 'multi-strategy not enabled') {
          this.multiStrategyEnabled = false
        } else {
          this.multiStrategyEnabled = false
        }

        if (allocRes?.data?.code === 1 && allocRes?.data?.data) {
          this.allocationData = allocRes.data.data
        }

        if (configRes?.data?.code === 1 && configRes?.data?.data) {
          this.configData = configRes.data.data
          this.expandedSymbols = Object.keys(this.configData.symbol_strategies || {})
          if (this.activeTabKey === 'config') this.loadConfigToForm()
        }

        if (strategiesRes?.data?.code === 1 && strategiesRes?.data?.data?.strategies) {
          this.strategies = strategiesRes.data.data.strategies
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
        vix_panic: rr.vix_panic ?? DEFAULT_REGIME_RULES.vix_panic,
        vix_high_vol: rr.vix_high_vol ?? DEFAULT_REGIME_RULES.vix_high_vol,
        vix_low_vol: rr.vix_low_vol ?? DEFAULT_REGIME_RULES.vix_low_vol
      }
      const ss = cfg.symbol_strategies || {}
      this.formSymbolStrategies = JSON.parse(JSON.stringify(ss))
      this.configExpandedSymbols = Object.keys(this.formSymbolStrategies)
    },
    beforeYamlUpload (file) {
      this.configLoading = true
      parseYamlConfig(file)
        .then(res => {
          if (res?.data?.code === 1 && res?.data?.data) {
            this.yamlPreview = res.data.data
          } else {
            this.$message.error(res?.data?.msg || 'Parse failed')
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
          vix_panic: p.regime_rules.vix_panic ?? DEFAULT_REGIME_RULES.vix_panic,
          vix_high_vol: p.regime_rules.vix_high_vol ?? DEFAULT_REGIME_RULES.vix_high_vol,
          vix_low_vol: p.regime_rules.vix_low_vol ?? DEFAULT_REGIME_RULES.vix_low_vol
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
        if (res?.data?.code === 1) {
          this.$message.success(this.$t('regime.saveSuccess') || this.$t('save.ok'))
          this.configData = { ...this.configData, ...body }
          this.multiStrategyEnabled = this.formEnabled
          this.loadData()
        } else {
          this.$message.error(res?.data?.msg || 'Save failed')
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
.summary-card .summary-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}
.summary-item {
  display: flex;
  align-items: center;
  gap: 8px;
  .label { color: #8c8c8c; font-size: 12px; }
  .weights-text { font-size: 12px; }
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
