<template>
  <div class="regime-switch-page">
    <a-tabs default-active-key="view">
      <!-- 查看 Tab -->
      <a-tab-pane :key="'view'" :tab="$t('regime.viewTab')">
        <div v-if="!multiStrategyEnabled" class="empty-hint">
          <a-alert
            type="info"
            :message="$t('regime.notEnabled')"
            show-icon
          />
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
        <div class="config-placeholder">
          <a-alert
            type="info"
            :message="$t('regime.configHint')"
            show-icon
          />
        </div>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script>
import { getSummary, getAllocation, getConfig, resetCircuitBreaker } from '@/api/multiStrategy'
import { getStrategyList } from '@/api/strategy'

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
      configData: { symbol_strategies: {} },
      strategies: [],
      expandedSymbols: [],
      resettingCb: false
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
</style>
