<template>
  <div class="regime-switch-page" :class="{ 'theme-dark': isDarkTheme }">
    <a-tabs v-model="activeTab" type="card">
      <a-tab-pane key="view" :tab="$t('regime.tabs.view')">
        <div class="view-tab">
          <!-- 顶部摘要 -->
          <div class="summary-cards">
            <a-card size="small" class="summary-card">
              <a-statistic :title="$t('regime.view.currentRegime')" :value="summary.regime || '-'" />
            </a-card>
            <a-card size="small" class="summary-card">
              <a-statistic :title="$t('regime.view.vix')" :value="summary.macro?.vix ?? '-'" :precision="1" />
            </a-card>
            <a-card size="small" class="summary-card">
              <a-statistic :title="$t('regime.view.fearGreed')" :value="summary.macro?.fear_greed ?? '-'" :precision="0" />
            </a-card>
            <a-card size="small" class="summary-card">
              <div class="weights-preview">
                <div class="label">{{ $t('regime.view.weights') }}</div>
                <div class="weights-values" v-if="Object.keys(summary.weights?.effective || {}).length">
                  <a-tag v-for="(v, k) in summary.weights?.effective" :key="k" size="small">{{ k }}: {{ (v * 100).toFixed(0) }}%</a-tag>
                </div>
                <div v-else>-</div>
              </div>
            </a-card>
            <a-card size="small" class="summary-card" v-if="summary.circuit_breaker?.triggered">
              <a-button type="danger" size="small" @click="handleResetCircuitBreaker">{{ $t('regime.view.resetCircuitBreaker') }}</a-button>
            </a-card>
          </div>

          <!-- 按 Symbol 分组的策略列表（可折叠） -->
          <a-card :title="$t('regime.view.strategyGroups')" class="strategy-groups-card">
            <a-spin :spinning="loadingView">
              <a-empty v-if="!loadingView && symbolGroups.length === 0" :description="$t('regime.view.noConfig')" />
              <a-collapse v-else v-model="expandedSymbols" accordion>
                <a-collapse-panel v-for="g in symbolGroups" :key="g.symbol" :header="g.header">
                  <div v-for="style in ['conservative','balanced','aggressive']" :key="style" class="style-row">
                    <span class="style-label">{{ style }}:</span>
                    <span class="style-strategies">
                      <template v-if="(g.styles[style] || []).length">
                        <a-tag v-for="s in g.styles[style]" :key="s.id" color="blue">{{ s.name || s.id }}</a-tag>
                        <span class="weight-hint" v-if="summary.weights?.effective?.[style]">({{ (summary.weights.effective[style] * 100).toFixed(0) }}%)</span>
                      </template>
                      <span v-else class="empty">-</span>
                    </span>
                  </div>
                </a-collapse-panel>
              </a-collapse>
            </a-spin>
          </a-card>
        </div>
      </a-tab-pane>

      <a-tab-pane key="config" :tab="$t('regime.tabs.config')">
        <div class="config-tab">
          <!-- 创建方式 -->
          <a-card :title="$t('regime.config.createMode')" size="small" class="config-section">
            <a-radio-group v-model="createMode" @change="onCreateModeChange">
              <a-radio value="form">{{ $t('regime.config.formMode') }}</a-radio>
              <a-radio value="yaml">{{ $t('regime.config.yamlMode') }}</a-radio>
            </a-radio-group>
            <div v-if="createMode === 'yaml'" class="yaml-upload">
              <a-upload
                :before-upload="handleYamlBeforeUpload"
                :show-upload-list="false"
                accept=".yaml,.yml">
                <a-button><a-icon type="upload" /> {{ $t('regime.config.uploadYaml') }}</a-button>
              </a-upload>
              <div v-if="yamlPreview" class="yaml-preview">
                <a-alert type="info" :message="$t('regime.config.yamlPreview')" showIcon />
                <pre>{{ JSON.stringify(yamlPreview, null, 2) }}</pre>
                <a-button type="primary" size="small" @click="applyYamlPreview" :loading="saving">{{ $t('regime.config.confirmSave') }}</a-button>
              </div>
            </div>
          </a-card>

          <!-- Regime 指标配置 -->
          <a-card v-if="createMode === 'form'" :title="$t('regime.config.indicatorTitle')" size="small" class="config-section">
            <div class="regime-indicator-config">
              <a-form-item :label="$t('regime.config.primaryIndicator')">
                <a-radio-group v-model="formConfig.regime_rules.primary_indicator" @change="onPrimaryIndicatorChange">
                  <a-radio value="vix">VIX</a-radio>
                  <a-radio value="fear_greed">Fear & Greed</a-radio>
                  <a-radio value="custom">{{ $t('regime.config.customCode') }}</a-radio>
                </a-radio-group>
              </a-form-item>
              <template v-if="formConfig.regime_rules.primary_indicator === 'custom'">
                <a-form-item :label="$t('regime.config.customCodeLabel')">
                  <a-textarea
                    v-model="formConfig.regime_rules.custom_code"
                    :placeholder="$t('regime.config.customCodePlaceholder')"
                    :rows="8"
                    style="font-family: monospace; font-size: 12px;"
                  />
                  <div class="indicator-hint">{{ $t('regime.config.customCodeHint') }}</div>
                  <a-button type="default" size="small" @click="verifyCustomCode" :loading="verifyingCode" style="margin-top: 8px;">
                    {{ $t('regime.config.verifyCode') }}
                  </a-button>
                  <span v-if="verifyResult" class="verify-result" :class="verifyResult.ok ? 'success' : 'error'">
                    {{ verifyResult.ok ? $t('regime.config.verifySuccess') + ': ' + verifyResult.regime : verifyResult.msg }}
                  </span>
                </a-form-item>
                <a-row :gutter="16">
                  <a-col :span="8">
                    <a-form-item :label="$t('regime.config.customScoreExtremeFear')">
                      <a-input-number v-model="formConfig.regime_rules.custom_score_extreme_fear" :min="0" :max="50" style="width:100%" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="8">
                    <a-form-item :label="$t('regime.config.customScoreHighFear')">
                      <a-input-number v-model="formConfig.regime_rules.custom_score_high_fear" :min="0" :max="60" style="width:100%" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="8">
                    <a-form-item :label="$t('regime.config.customScoreLowGreed')">
                      <a-input-number v-model="formConfig.regime_rules.custom_score_low_greed" :min="40" :max="100" style="width:100%" />
                    </a-form-item>
                  </a-col>
                </a-row>
                <div class="indicator-hint">{{ $t('regime.config.customScoreHint') }}</div>
              </template>
              <template v-else-if="formConfig.regime_rules.primary_indicator === 'vix'">
                <a-row :gutter="16">
                  <a-col :span="8">
                    <a-form-item :label="$t('regime.config.vixPanic')">
                      <a-input-number v-model="formConfig.regime_rules.vix_panic" :min="10" :max="80" style="width:100%" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="8">
                    <a-form-item :label="$t('regime.config.vixHighVol')">
                      <a-input-number v-model="formConfig.regime_rules.vix_high_vol" :min="10" :max="50" style="width:100%" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="8">
                    <a-form-item :label="$t('regime.config.vixLowVol')">
                      <a-input-number v-model="formConfig.regime_rules.vix_low_vol" :min="5" :max="25" style="width:100%" />
                    </a-form-item>
                  </a-col>
                </a-row>
                <div class="indicator-hint">{{ $t('regime.config.vixHint') }}</div>
              </template>
              <template v-else-if="formConfig.regime_rules.primary_indicator === 'fear_greed'">
                <a-row :gutter="16">
                  <a-col :span="8">
                    <a-form-item :label="$t('regime.config.fgExtremeFear')">
                      <a-input-number v-model="formConfig.regime_rules.fg_extreme_fear" :min="0" :max="50" style="width:100%" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="8">
                    <a-form-item :label="$t('regime.config.fgHighFear')">
                      <a-input-number v-model="formConfig.regime_rules.fg_high_fear" :min="0" :max="60" style="width:100%" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="8">
                    <a-form-item :label="$t('regime.config.fgLowGreed')">
                      <a-input-number v-model="formConfig.regime_rules.fg_low_greed" :min="40" :max="100" style="width:100%" />
                    </a-form-item>
                  </a-col>
                </a-row>
                <div class="indicator-hint">{{ $t('regime.config.fgHint') }}</div>
              </template>
            </div>
          </a-card>

          <!-- 策略绑定（表单模式） -->
          <a-card v-if="createMode === 'form'" :title="$t('regime.config.strategyBinding')" size="small" class="config-section">
            <div class="symbol-bindings">
              <div v-for="(symData, symbol) in formConfig.symbol_strategies" :key="symbol" class="symbol-row">
                <a-input :value="symbol" @change="e => renameSymbol(symbol, e.target.value)" size="small" style="width:120px" placeholder="Symbol" />
                <div class="style-selects">
                  <div v-for="style in ['conservative','balanced','aggressive']" :key="style" class="style-select">
                    <span class="style-label">{{ style }}:</span>
                    <a-select
                      mode="multiple"
                      :value="symData[style] || []"
                      @change="v => setSymbolStyle(symbol, style, v)"
                      placeholder="-"
                      size="small"
                      style="min-width:160px"
                    >
                      <a-select-option v-for="s in strategyOptions" :key="s.id" :value="s.id">{{ s.strategy_name }}</a-select-option>
                    </a-select>
                  </div>
                </div>
                <a-button type="link" danger size="small" @click="removeSymbol(symbol)"><a-icon type="delete" /></a-button>
              </div>
              <a-button @click="addSymbol" size="small"><a-icon type="plus" /> {{ $t('regime.config.addSymbol') }}</a-button>
            </div>
          </a-card>

          <!-- 权重配置 -->
          <a-card v-if="createMode === 'form'" :title="$t('regime.config.weights')" size="small" class="config-section">
            <a-table
              :columns="weightColumns"
              :data-source="weightTableData"
              :pagination="false"
              size="small"
              bordered
            >
              <template slot="conservative" slot-scope="text, record">
                <a-input-number v-model="formConfig.regime_to_weights[record.regime].conservative" :min="0" :max="1" :step="0.1" :precision="2" size="small" style="width:80px" />
              </template>
              <template slot="balanced" slot-scope="text, record">
                <a-input-number v-model="formConfig.regime_to_weights[record.regime].balanced" :min="0" :max="1" :step="0.1" :precision="2" size="small" style="width:80px" />
              </template>
              <template slot="aggressive" slot-scope="text, record">
                <a-input-number v-model="formConfig.regime_to_weights[record.regime].aggressive" :min="0" :max="1" :step="0.1" :precision="2" size="small" style="width:80px" />
              </template>
            </a-table>
            <a-checkbox v-model="formConfig.multi_strategy_enabled">{{ $t('regime.config.enableMultiStrategy') }}</a-checkbox>
          </a-card>

          <a-button v-if="createMode === 'form'" type="primary" @click="saveConfig" :loading="saving">{{ $t('regime.config.save') }}</a-button>
        </div>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script>
import { getSummary, getConfig, putConfig, parseYamlConfig, resetCircuitBreaker, verifyCustomRegimeCode } from '@/api/multiStrategy'
import { getStrategyList } from '@/api/strategy'
import { baseMixin } from '@/store/app-mixin'

const REGIMES = ['panic', 'high_vol', 'normal', 'low_vol']
const STYLES = ['conservative', 'balanced', 'aggressive']

const DEFAULT_WEIGHTS = {
  panic: { conservative: 0.8, balanced: 0.2, aggressive: 0 },
  high_vol: { conservative: 0.5, balanced: 0.4, aggressive: 0.1 },
  normal: { conservative: 0.2, balanced: 0.6, aggressive: 0.2 },
  low_vol: { conservative: 0.1, balanced: 0.3, aggressive: 0.6 }
}

export default {
  name: 'RegimeSwitch',
  mixins: [baseMixin],
  data () {
    return {
      activeTab: 'view',
      loadingView: false,
      saving: false,
      summary: {
        regime: '',
        macro: {},
        weights: {},
        circuit_breaker: {}
      },
      symbolGroups: [],
      expandedSymbols: [],
      strategies: [],
      createMode: 'form',
      yamlPreview: null,
      verifyingCode: false,
      verifyResult: null,
      formConfig: {
        symbol_strategies: {},
        regime_to_weights: { ...JSON.parse(JSON.stringify(DEFAULT_WEIGHTS)) },
        regime_rules: {
          primary_indicator: 'vix',
          vix_panic: 30,
          vix_high_vol: 25,
          vix_low_vol: 15,
          fg_extreme_fear: 20,
          fg_high_fear: 35,
          fg_low_greed: 65,
          custom_code: '',
          custom_score_extreme_fear: 20,
          custom_score_high_fear: 35,
          custom_score_low_greed: 65
        },
        multi_strategy_enabled: true
      }
    }
  },
  computed: {
    isDarkTheme () {
      return this.navTheme === 'dark' || this.navTheme === 'realdark'
    },
    navTheme () {
      return this.$store.state.app.theme
    },
    strategyOptions () {
      return this.strategies.map(s => ({
        id: s.id,
        strategy_name: `${s.strategy_name || s.id} (${(s.trading_config || {}).symbol || '-'})`
      }))
    },
    weightColumns () {
      return [
        { title: 'Regime', dataIndex: 'regime', key: 'regime', width: 100 },
        { title: 'Conservative', key: 'conservative', scopedSlots: { customRender: 'conservative' } },
        { title: 'Balanced', key: 'balanced', scopedSlots: { customRender: 'balanced' } },
        { title: 'Aggressive', key: 'aggressive', scopedSlots: { customRender: 'aggressive' } }
      ]
    },
    weightTableData () {
      return REGIMES.map(r => ({
        key: r,
        regime: r,
        ...this.formConfig.regime_to_weights[r]
      }))
    }
  },
  mounted () {
    this.loadStrategies()
    this.loadFormConfig()
    this.loadViewData()
  },
  methods: {
    async loadViewData () {
      this.loadingView = true
      try {
        const res = await getSummary()
        if (res.code === 1 && res.data) {
          this.summary = res.data
        } else if (res.code === 1 && !res.data) {
          this.summary = {}
        }
        const cfgRes = await getConfig()
        if (cfgRes.code === 1 && cfgRes.data) {
          this.buildSymbolGroups(cfgRes.data)
        }
      } catch (e) {
        this.$message.error(e.message || 'Load failed')
      } finally {
        this.loadingView = false
      }
    },
    buildSymbolGroups (config) {
      const ss = config.symbol_strategies || {}
      const idToName = Object.fromEntries(this.strategies.map(s => [s.id, s.strategy_name]))
      this.symbolGroups = Object.entries(ss).map(([symbol, styles]) => {
        const stylesWithNames = {}
        for (const style of STYLES) {
          const ids = styles[style] || []
          stylesWithNames[style] = ids.map(id => ({ id, name: idToName[id] || id }))
        }
        return {
          symbol,
          header: `${symbol} (${Object.values(stylesWithNames).flat().length} strategies)`,
          styles: stylesWithNames
        }
      })
    },
    async loadStrategies () {
      try {
        const res = await getStrategyList()
        if (res.code === 1 && res.data?.strategies) {
          this.strategies = res.data.strategies
        }
      } catch (e) {
        console.warn('load strategies failed', e)
      }
    },
    async loadFormConfig () {
      try {
        const res = await getConfig()
        if (res.code === 1 && res.data) {
          const d = res.data
          this.formConfig.symbol_strategies = d.symbol_strategies || {}
          const rtw = d.regime_to_weights || {}
          this.formConfig.regime_to_weights = Object.assign({}, JSON.parse(JSON.stringify(DEFAULT_WEIGHTS)), rtw)
          const rr = d.regime_rules || {}
          this.formConfig.regime_rules = Object.assign({
            primary_indicator: 'vix',
            vix_panic: 30,
            vix_high_vol: 25,
            vix_low_vol: 15,
            fg_extreme_fear: 20,
            fg_high_fear: 35,
            fg_low_greed: 65,
            custom_code: '',
            custom_score_extreme_fear: 20,
            custom_score_high_fear: 35,
            custom_score_low_greed: 65
          }, rr)
          this.formConfig.multi_strategy_enabled = (d.multi_strategy || {}).enabled !== false
        }
      } catch (e) {
        console.warn('load config failed', e)
      }
    },
    addSymbol () {
      const sym = `SYM${Date.now().toString(36)}`
      this.$set(this.formConfig.symbol_strategies, sym, { conservative: [], balanced: [], aggressive: [] })
    },
    removeSymbol (symbol) {
      this.$delete(this.formConfig.symbol_strategies, symbol)
    },
    renameSymbol (oldSym, newSym) {
      if (!newSym || newSym === oldSym) return
      const v = this.formConfig.symbol_strategies[oldSym]
      this.$delete(this.formConfig.symbol_strategies, oldSym)
      this.$set(this.formConfig.symbol_strategies, newSym, v)
    },
    setSymbolStyle (symbol, style, ids) {
      if (!this.formConfig.symbol_strategies[symbol]) {
        this.$set(this.formConfig.symbol_strategies, symbol, { conservative: [], balanced: [], aggressive: [] })
      }
      this.$set(this.formConfig.symbol_strategies[symbol], style, ids)
    },
    onCreateModeChange () {
      if (this.createMode === 'form') this.yamlPreview = null
    },
    onPrimaryIndicatorChange () {
      this.verifyResult = null
    },
    handleYamlBeforeUpload (file) {
      parseYamlConfig(file).then(res => {
        if (res.code === 1 && res.data) {
          this.yamlPreview = res.data
          this.$message.success(this.$t('regime.config.yamlParsed'))
        } else {
          this.$message.error(res.msg || 'Parse failed')
        }
      }).catch(e => this.$message.error(e.message || 'Parse failed'))
      return false
    },
    async applyYamlPreview () {
      if (!this.yamlPreview) return
      this.saving = true
      try {
        const ms = this.yamlPreview.multi_strategy || {}
        ms.enabled = ms.enabled !== false
        if (this.yamlPreview.regime_to_weights) ms.regime_to_weights = this.yamlPreview.regime_to_weights
        const res = await putConfig({
          symbol_strategies: this.yamlPreview.symbol_strategies || {},
          regime_to_weights: (this.yamlPreview.multi_strategy || {}).regime_to_weights || this.yamlPreview.regime_to_weights || {},
          regime_rules: this.yamlPreview.regime_rules || {},
          multi_strategy: ms
        })
        if (res.code === 1) {
          this.$message.success(this.$t('regime.config.saved'))
          this.yamlPreview = null
          this.loadViewData()
          this.loadFormConfig()
        } else {
          this.$message.error(res.msg || 'Save failed')
        }
      } finally {
        this.saving = false
      }
    },
    async saveConfig () {
      const ms = { enabled: this.formConfig.multi_strategy_enabled, regime_to_weights: this.formConfig.regime_to_weights }
      this.saving = true
      try {
        const res = await putConfig({
          symbol_strategies: this.formConfig.symbol_strategies,
          regime_to_weights: this.formConfig.regime_to_weights,
          regime_rules: this.formConfig.regime_rules,
          multi_strategy: ms
        })
        if (res.code === 1) {
          this.$message.success(this.$t('regime.config.saved'))
          this.loadViewData()
        } else {
          this.$message.error(res.msg || 'Save failed')
        }
      } finally {
        this.saving = false
      }
    },
    async verifyCustomCode () {
      if (!(this.formConfig.regime_rules.custom_code || '').trim()) {
        this.$message.warning(this.$t('regime.config.customCodeRequired'))
        return
      }
      this.verifyingCode = true
      this.verifyResult = null
      try {
        const res = await verifyCustomRegimeCode({
          custom_code: this.formConfig.regime_rules.custom_code,
          regime_rules: this.formConfig.regime_rules
        })
        if (res.code === 1 && res.data) {
          this.verifyResult = { ok: true, regime: res.data.regime }
          this.$message.success(this.$t('regime.config.verifySuccess') + ': ' + res.data.regime)
        } else {
          this.verifyResult = { ok: false, msg: res.msg || 'Verify failed' }
        }
      } catch (e) {
        this.verifyResult = { ok: false, msg: e.message || 'Verify failed' }
      } finally {
        this.verifyingCode = false
      }
    },
    async handleResetCircuitBreaker () {
      try {
        await resetCircuitBreaker()
        this.$message.success(this.$t('regime.view.resetSuccess'))
        this.loadViewData()
      } catch (e) {
        this.$message.error(e.message || 'Reset failed')
      }
    }
  }
}
</script>

<style lang="less" scoped>
.regime-switch-page {
  padding: 16px;
}
.summary-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  .summary-card {
    min-width: 140px;
  }
  .weights-preview {
    .label { font-size: 12px; color: #999; margin-bottom: 4px; }
    .weights-values { display: flex; flex-wrap: wrap; gap: 4px; }
  }
}
.strategy-groups-card {
  margin-top: 16px;
}
.style-row {
  margin-bottom: 8px;
  .style-label { font-weight: 500; margin-right: 8px; min-width: 90px; display: inline-block; }
  .style-strategies .empty { color: #999; }
  .weight-hint { margin-left: 8px; color: #666; font-size: 12px; }
}
.config-section {
  margin-bottom: 16px;
}
.yaml-upload { margin-top: 8px; }
.yaml-preview {
  margin-top: 12px;
  pre { font-size: 12px; max-height: 200px; overflow: auto; }
}
.indicator-hint {
  font-size: 12px;
  color: #999;
  margin-top: 8px;
}
.verify-result {
  margin-left: 12px;
  font-size: 12px;
}
.verify-result.success { color: #52c41a; }
.verify-result.error { color: #ff4d4f; }
.regime-indicator-config .ant-form-item { margin-bottom: 12px; }
.symbol-bindings .symbol-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  .style-selects { display: flex; gap: 16px; flex-wrap: wrap; }
  .style-select { display: flex; align-items: center; gap: 4px; }
}
</style>
