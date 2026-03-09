
<template>
  <div class="broker-dashboard" :class="{ 'theme-dark': isDarkTheme }">
    <!-- 连接状态横幅 -->
    <div class="connection-bar" :class="connected ? 'connected' : 'disconnected'">
      <div class="conn-left">
        <span class="conn-dot"></span>
        <span class="conn-label">
          {{ connected ? $t('broker.connected') : $t('broker.disconnected') }}
        </span>
        <span v-if="accountId" class="conn-account">{{ accountId }}</span>
      </div>
      <div class="conn-right">
        <a-button
          v-if="!connected"
          type="primary"
          size="small"
          :loading="connecting"
          @click="handleConnect"
        >
          <a-icon type="api" /> {{ $t('broker.connect') }}
        </a-button>
        <a-button
          v-else
          size="small"
          @click="handleDisconnect"
        >
          <a-icon type="disconnect" /> {{ $t('broker.disconnect') }}
        </a-button>
        <a-button size="small" :loading="loading" @click="fetchData" style="margin-left: 8px;">
          <a-icon type="reload" />
        </a-button>
      </div>
    </div>

    <!-- KPI 指标卡片 -->
    <div class="kpi-grid">
      <!-- 总权益 -->
      <div class="kpi-card kpi-primary">
        <div class="kpi-glow"></div>
        <div class="kpi-content">
          <div class="kpi-header">
            <span class="kpi-icon"><a-icon type="wallet" /></span>
            <span class="kpi-label">{{ $t('broker.netLiquidation') }}</span>
          </div>
          <div class="kpi-value">
            <span class="currency">{{ accountCurrency }} </span>
            <span class="amount">{{ formatNumber(netLiquidation) }}</span>
          </div>
          <div class="kpi-sub">
            <span class="currency">{{ accountCurrency }} </span>
            <span :class="unrealizedPnl >= 0 ? 'positive' : 'negative'">
              {{ unrealizedPnl >= 0 ? '+' : '' }}{{ formatNumber(unrealizedPnl) }}
            </span>
            <span class="label">{{ $t('broker.unrealizedPnl') }}</span>
          </div>
        </div>
      </div>

      <!-- 胜率 -->
      <div class="kpi-card kpi-win-rate">
        <div class="kpi-content">
          <div class="kpi-header">
            <span class="kpi-icon"><a-icon type="trophy" /></span>
            <span class="kpi-label">{{ $t('broker.winRate') }}</span>
          </div>
          <div class="kpi-value">
            <span class="amount">{{ formatNumber(performance.win_rate, 1) }}</span>
            <span class="unit">%</span>
          </div>
          <div class="kpi-sub">
            <span class="positive">{{ performance.winning_trades || 0 }}</span>
            <span class="label">{{ $t('broker.win') }}</span>
            <span class="divider">/</span>
            <span class="negative">{{ performance.losing_trades || 0 }}</span>
            <span class="label">{{ $t('broker.lose') }}</span>
          </div>
        </div>
        <div class="kpi-ring">
          <svg viewBox="0 0 36 36">
            <path class="ring-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
            <path class="ring-progress" :stroke-dasharray="`${performance.win_rate || 0}, 100`" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
          </svg>
        </div>
      </div>

      <!-- 盈亏比 -->
      <div class="kpi-card kpi-profit-factor">
        <div class="kpi-content">
          <div class="kpi-header">
            <span class="kpi-icon"><a-icon type="rise" /></span>
            <span class="kpi-label">{{ $t('broker.profitFactor') }}</span>
          </div>
          <div class="kpi-value">
            <span class="amount">{{ formatNumber(performance.profit_factor, 2) }}</span>
            <span class="unit">:1</span>
          </div>
          <div class="kpi-sub">
            <span>{{ $t('broker.avgWin') }} </span>
            <span class="positive">{{ formatNumber(performance.avg_win) }}</span>
          </div>
        </div>
      </div>

      <!-- 总交易量 -->
      <div class="kpi-card kpi-trades">
        <div class="kpi-content">
          <div class="kpi-header">
            <span class="kpi-icon"><a-icon type="swap" /></span>
            <span class="kpi-label">{{ $t('broker.totalTrades') }}</span>
          </div>
          <div class="kpi-value">
            <span class="amount">{{ performance.total_trades || 0 }}</span>
            <span class="unit">{{ $t('broker.unit.trades') }}</span>
          </div>
          <div class="kpi-sub">
            <span class="positive">+{{ formatNumber(performance.total_profit) }}</span>
            <span class="divider">/</span>
            <span class="negative">-{{ formatNumber(performance.total_loss) }}</span>
          </div>
        </div>
      </div>

      <!-- 可用资金 -->
      <div class="kpi-card kpi-cash">
        <div class="kpi-content">
          <div class="kpi-header">
            <span class="kpi-icon"><a-icon type="dollar" /></span>
            <span class="kpi-label">{{ $t('broker.availableFunds') }}</span>
          </div>
          <div class="kpi-value">
            <span class="amount">{{ formatNumber(getAccountValue('AvailableFunds')) }}</span>
          </div>
          <div class="kpi-sub">
            <span class="label">{{ $t('broker.buyingPower') }} </span>
            <span>{{ formatNumber(getAccountValue('BuyingPower')) }}</span>
          </div>
        </div>
      </div>

      <!-- 已实现盈亏 -->
      <div class="kpi-card kpi-realized">
        <div class="kpi-content">
          <div class="kpi-header">
            <span class="kpi-icon"><a-icon type="check-circle" /></span>
            <span class="kpi-label">{{ $t('broker.realizedPnl') }}</span>
          </div>
          <div class="kpi-value">
            <span class="currency">{{ accountCurrency }} </span>
            <span class="amount" :class="realizedPnl >= 0 ? 'positive' : 'negative'">
              {{ realizedPnl >= 0 ? '+' : '' }}{{ formatNumber(realizedPnl) }}
            </span>
          </div>
          <div class="kpi-sub">
            <span class="label">{{ $t('broker.marginUsed') }} </span>
            <span>{{ formatNumber(getAccountValue('InitMarginReq')) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 当前持仓 -->
    <div class="chart-panel">
      <div class="panel-header">
        <div class="panel-title">
          <a-icon type="stock" />
          <span>{{ $t('broker.currentPositions') }}</span>
        </div>
        <div class="panel-badge">{{ positions.length }}</div>
      </div>
      <a-table
        :columns="positionColumns"
        :data-source="positions"
        :rowKey="(r, i) => r.symbol + '-' + i"
        :pagination="false"
        size="small"
        :scroll="{ x: 'max-content' }"
        class="pro-table"
        :locale="{ emptyText: $t('broker.noPositions') }"
      >
        <template slot="symbol" slot-scope="text, record">
          <div class="symbol-cell">
            <span class="symbol-name">{{ text }}</span>
            <span class="symbol-strategy">{{ record.secType }} · {{ record.exchange }}</span>
          </div>
        </template>
        <template slot="quantity" slot-scope="text">
          <span :class="text > 0 ? 'positive' : text < 0 ? 'negative' : ''">
            {{ text }}
          </span>
        </template>
        <template slot="avgCost" slot-scope="text">
          {{ formatNumber(text) }}
        </template>
        <template slot="marketValue" slot-scope="text, record">
          <div>{{ record.currency }} {{ formatNumber(text) }}</div>
        </template>
        <template slot="commission" slot-scope="text">
          <!-- eslint-disable-next-line vue/no-unused-vars -->
          <span v-if="text" class="negative">
            -{{ formatNumber(text) }}
          </span>
          <span v-else class="text-muted">0</span>
        </template>
        <template slot="unrealizedPnL" slot-scope="text, record">
          <span :class="(text - (record.commission || 0)) >= 0 ? 'positive' : 'negative'">
            {{ (text - (record.commission || 0)) >= 0 ? '+' : '' }}{{ formatNumber(text - (record.commission || 0)) }}
          </span>
        </template>
      </a-table>
    </div>

    <!-- 挂单 -->
    <div class="chart-panel">
      <div class="panel-header">
        <div class="panel-title">
          <a-icon type="clock-circle" />
          <span>{{ $t('broker.openOrders') }}</span>
        </div>
        <div class="panel-badge">{{ openOrders.length }}</div>
      </div>
      <a-table
        :columns="orderColumns"
        :data-source="openOrders"
        :rowKey="(r, i) => r.orderId + '-' + i"
        :pagination="false"
        size="small"
        :scroll="{ x: 'max-content' }"
        class="pro-table"
        :locale="{ emptyText: $t('broker.noOrders') }"
      >
        <template slot="action" slot-scope="text">
          <span class="side-tag" :class="text === 'BUY' ? 'long' : 'short'">
            {{ text }}
          </span>
        </template>
        <template slot="status" slot-scope="text">
          <span class="status-tag" :class="text.toLowerCase()">{{ text }}</span>
        </template>
        <template slot="progress" slot-scope="text, record">
          <div>{{ record.filled }} / {{ record.quantity }}</div>
          <div class="progress-bar-wrap">
            <div class="progress-bar-fill" :style="{ width: (record.quantity > 0 ? record.filled / record.quantity * 100 : 0) + '%' }"></div>
          </div>
        </template>
      </a-table>
    </div>

    <!-- 最近交易 -->
    <div class="chart-panel">
      <div class="panel-header">
        <div class="panel-title">
          <a-icon type="history" />
          <span>{{ $t('broker.recentTrades') }}</span>
          <span class="source-tag">QuantDinger</span>
        </div>
      </div>
      <a-table
        :columns="tradeColumns"
        :data-source="recentTrades"
        rowKey="id"
        :pagination="{ pageSize: 10, size: 'small' }"
        size="small"
        :scroll="{ x: 'max-content' }"
        class="pro-table"
        :locale="{ emptyText: $t('broker.noTrades') }"
      >
        <template slot="type" slot-scope="text">
          <span class="type-tag" :class="getTypeClass(text)">
            {{ getSignalTypeText(text) }}
          </span>
        </template>
        <template slot="profit" slot-scope="text">
          <span v-if="text !== null && text !== undefined" :class="text >= 0 ? 'positive' : 'negative'">
            {{ text >= 0 ? '+' : '' }}{{ formatNumber(text) }}
          </span>
          <span v-else class="text-muted">--</span>
        </template>
        <template slot="time" slot-scope="text">
          <span class="time-cell">{{ formatTime(text) }}</span>
        </template>
      </a-table>
    </div>

    <!-- 执单记录 -->
    <div class="chart-panel">
      <div class="panel-header">
        <div class="panel-title">
          <a-icon type="unordered-list" />
          <span>{{ $t('broker.executions') }}</span>
          <span class="source-tag">QuantDinger</span>
        </div>
        <a-select
          v-model="executionFilter"
          size="small"
          style="width: 100px; margin-left: auto;"
        >
          <a-select-option value="all">全部</a-select-option>
          <a-select-option value="completed">成功</a-select-option>
          <a-select-option value="failed">失败</a-select-option>
        </a-select>
        <div class="panel-badge">{{ filteredExecutions.length }}</div>
      </div>
      <a-table
        :columns="executionColumns"
        :data-source="filteredExecutions"
        rowKey="id"
        :pagination="{ pageSize: 15, size: 'small', showSizeChanger: true }"
        size="small"
        :scroll="{ x: 1400 }"
        class="pro-table"
        :locale="{ emptyText: $t('broker.noExecutions') }"
      >
        <template slot="strategy_name" slot-scope="text, record">
          <div class="symbol-cell">
            <span class="symbol-name">{{ text || '-' }}</span>
            <span class="symbol-strategy">ID: {{ record.strategy_id }}</span>
          </div>
        </template>
        <template slot="symbol" slot-scope="text">
          <span class="symbol-tag">{{ text }}</span>
        </template>
        <template slot="signal_type" slot-scope="text">
          <span class="type-tag" :class="getTypeClass(text)">
            {{ getSignalTypeText(text) }}
          </span>
        </template>
        <template slot="exec_status" slot-scope="text, record">
          <span class="status-tag" :class="text">
            {{ getStatusText(text) }}
          </span>
          <div v-if="text === 'failed' && record.error_message" class="error-hint">
            <a-tooltip :title="record.error_message">
              <a-icon type="exclamation-circle" />
              <span>{{ $t('broker.viewError') }}</span>
            </a-tooltip>
          </div>
        </template>
        <template slot="exec_amount" slot-scope="text, record">
          <div>{{ formatQuantity(text) }}</div>
          <div v-if="record.filled_amount" class="sub-text">
            {{ $t('broker.filled') }}: {{ formatQuantity(record.filled_amount) }}
          </div>
        </template>
        <template slot="exec_price" slot-scope="text, record">
          <div v-if="record.filled_price">{{ formatNumber(record.filled_price) }}</div>
          <div v-else class="text-muted">-</div>
        </template>
        <template slot="slippage" slot-scope="text, record">
          <div v-if="text !== null && text !== undefined">
            <span :class="text > 0 ? 'negative' : text < 0 ? 'positive' : ''">
              {{ text > 0 ? '+' : '' }}{{ formatNumber(text, 4) }}
            </span>
            <div v-if="record.slippage_pct !== null" class="sub-text">
              {{ record.slippage_pct > 0 ? '+' : '' }}{{ record.slippage_pct }}%
            </div>
          </div>
          <span v-else class="text-muted">--</span>
        </template>
        <template slot="time_info" slot-scope="text, record">
          <div class="time-cell">{{ formatTime(record.created_at) }}</div>
          <div v-if="record.executed_at" class="sub-text">
            {{ formatTime(record.executed_at) }}
          </div>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script>
import { getIbkrDashboard, connectIbkr, disconnectIbkr } from '@/api/ibkr'
import { mapState } from 'vuex'

export default {
  name: 'BrokerDashboard',
  data () {
    return {
      loading: false,
      connecting: false,
      connected: false,
      accountId: '',
      accountCurrency: 'USD',
      accountItems: {},
      positions: [],
      openOrders: [],
      recentTrades: [],
      executions: [],
      executionFilter: 'all',
      performance: {},
      refreshTimer: null
    }
  },
  computed: {
    ...mapState({
      navTheme: state => state.app.theme
    }),
    isDarkTheme () {
      return this.navTheme === 'dark' || this.navTheme === 'realdark'
    },
    netLiquidation () {
      return this.getAccountValue('NetLiquidation')
    },
    unrealizedPnl () {
      return this.getAccountValue('UnrealizedPnL')
    },
    realizedPnl () {
      const live = this.getAccountValue('RealizedPnL')
      if (live !== 0) return live
      return this.performance.total_realized_pnl || 0
    },
    positionColumns () {
      return [
        { title: this.$t('broker.col.symbol'), dataIndex: 'symbol', scopedSlots: { customRender: 'symbol' }, width: 120 },
        { title: '币种', dataIndex: 'currency', width: 80 },
        { title: this.$t('broker.col.quantity'), dataIndex: 'quantity', scopedSlots: { customRender: 'quantity' }, width: 100, align: 'right' },
        { title: this.$t('broker.col.avgCost'), dataIndex: 'avgCost', scopedSlots: { customRender: 'avgCost' }, width: 100, align: 'right' },
        { title: this.$t('broker.col.marketValue'), dataIndex: 'marketValue', scopedSlots: { customRender: 'marketValue' }, width: 140, align: 'right' },
        { title: '佣金', dataIndex: 'commission', scopedSlots: { customRender: 'commission' }, width: 100, align: 'right' },
        { title: this.$t('broker.unrealizedPnl'), dataIndex: 'unrealizedPnL', scopedSlots: { customRender: 'unrealizedPnL' }, width: 120, align: 'right' }
      ]
    },
    orderColumns () {
      return [
        { title: 'ID', dataIndex: 'orderId', width: 80, align: 'left' },
        { title: this.$t('broker.col.symbol'), dataIndex: 'symbol', width: 100, align: 'left' },
        { title: this.$t('broker.col.action'), dataIndex: 'action', scopedSlots: { customRender: 'action' }, width: 80, align: 'left' },
        { title: this.$t('broker.col.type'), dataIndex: 'orderType', width: 80, align: 'left' },
        { title: this.$t('broker.col.quantity'), dataIndex: 'quantity', width: 80, align: 'right' },
        { title: this.$t('broker.col.limitPrice'), dataIndex: 'limitPrice', customRender: (t) => t ? this.formatNumber(t) : '-', width: 100, align: 'right' },
        { title: this.$t('broker.col.status'), dataIndex: 'status', scopedSlots: { customRender: 'status' }, width: 100, align: 'left' },
        { title: this.$t('broker.col.progress'), dataIndex: 'filled', scopedSlots: { customRender: 'progress' }, width: 120, align: 'right' }
      ]
    },
    tradeColumns () {
      return [
        { title: this.$t('broker.col.time'), dataIndex: 'created_at', scopedSlots: { customRender: 'time' }, width: 160, align: 'left' },
        { title: this.$t('broker.col.strategy'), dataIndex: 'strategy_name', width: 120, align: 'left' },
        { title: this.$t('broker.col.symbol'), dataIndex: 'symbol', width: 90, align: 'left' },
        { title: this.$t('broker.col.signalType'), dataIndex: 'type', scopedSlots: { customRender: 'type' }, width: 100, align: 'left' },
        { title: this.$t('broker.col.price'), dataIndex: 'price', customRender: (t) => this.formatNumber(t), width: 100, align: 'right' },
        { title: this.$t('broker.col.profit'), dataIndex: 'profit', scopedSlots: { customRender: 'profit' }, width: 110, align: 'right' }
      ]
    },
    executionColumns () {
      return [
        { title: this.$t('broker.col.strategy'), dataIndex: 'strategy_name', scopedSlots: { customRender: 'strategy_name' }, width: 130, align: 'left' },
        { title: this.$t('broker.col.symbol'), dataIndex: 'symbol', scopedSlots: { customRender: 'symbol' }, width: 90, align: 'left' },
        { title: this.$t('broker.col.signalType'), dataIndex: 'signal_type', scopedSlots: { customRender: 'signal_type' }, width: 90, align: 'left' },
        { title: this.$t('broker.col.amount'), dataIndex: 'amount', scopedSlots: { customRender: 'exec_amount' }, width: 120, align: 'right' },
        { title: this.$t('broker.col.signalPrice'), dataIndex: 'signal_price', customRender: (t) => t ? this.formatNumber(t) : '-', width: 100, align: 'right' },
        { title: this.$t('broker.col.fillPrice'), dataIndex: 'filled_price', scopedSlots: { customRender: 'exec_price' }, width: 100, align: 'right' },
        { title: this.$t('broker.col.slippage'), dataIndex: 'slippage', scopedSlots: { customRender: 'slippage' }, width: 100, align: 'right' },
        { title: this.$t('broker.col.status'), dataIndex: 'status', scopedSlots: { customRender: 'exec_status' }, width: 100, align: 'left' },
        { title: this.$t('broker.col.timeInfo'), dataIndex: 'created_at', scopedSlots: { customRender: 'time_info' }, width: 150, align: 'left' }
      ]
    },
    filteredExecutions () {
      if (this.executionFilter === 'all') {
        return this.executions
      }
      return this.executions.filter(item => item.status === this.executionFilter)
    }
  },
  mounted () {
    this.fetchData()
    this._startPolling(30000)
  },
  beforeDestroy () {
    this._stopPolling()
  },
  methods: {
    _startPolling (interval) {
      this._stopPolling()
      this._pollInterval = interval
      this.refreshTimer = setInterval(() => { this.fetchData() }, interval)
    },
    _stopPolling () {
      if (this.refreshTimer) {
        clearInterval(this.refreshTimer)
        this.refreshTimer = null
      }
    },
    async fetchData () {
      this.loading = true
      try {
        const res = await getIbkrDashboard()
        if (res.code === 1 && res.data) {
          const d = res.data
          const wasConnected = this.connected
          this.connected = d.connected || false
          this.accountId = (d.account && d.account.account_id) || (d.connection && d.connection.account) || ''
          this.accountCurrency = (d.account && d.account.currency) || 'USD'
          this.accountItems = (d.account && d.account.items) || {}
          this.positions = d.positions || []
          this.openOrders = d.open_orders || []
          this.recentTrades = d.recent_trades || []
          this.executions = d.executions || []
          this.performance = d.performance || {}

          if (!this.connected && wasConnected) {
            this.$message.warning('IBKR 连接已断开，正在尝试自动重连...')
            this._startPolling(5000)
          } else if (this.connected && !wasConnected && this._pollInterval === 5000) {
            this.$message.success('IBKR 连接已恢复')
            this._startPolling(30000)
          }
        }
      } catch (e) {
        console.error('Failed to fetch IBKR dashboard:', e)
      } finally {
        this.loading = false
      }
    },
    async handleConnect () {
      this.connecting = true
      try {
        await connectIbkr({})
        this.$message.success(this.$t('broker.connectSuccess'))
        await this.fetchData()
      } catch (e) {
        this.$message.error(this.$t('broker.connectFailed'))
      } finally {
        this.connecting = false
      }
    },
    async handleDisconnect () {
      try {
        await disconnectIbkr()
        this.$message.info(this.$t('broker.disconnectSuccess'))
        this.connected = false
        this.positions = []
        this.openOrders = []
        this.accountItems = {}
      } catch (e) {
        this.$message.error(this.$t('broker.disconnectFailed'))
      }
    },
    getAccountValue (tag) {
      const item = this.accountItems[tag]
      return item ? (item.value || 0) : 0
    },
    formatNumber (num, digits = 2) {
      if (num === undefined || num === null) return '0.00'
      return Number(num).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
    },
    formatQuantity (num) {
      if (num === undefined || num === null) return '-'
      const n = Number(num)
      if (isNaN(n)) return '-'
      if (n % 1 === 0) {
        return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
      }
      return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    },
    formatTime (timestamp) {
      if (!timestamp) return '-'
      try {
        let date
        if (typeof timestamp === 'string' && timestamp.includes('-') && timestamp.includes(':')) {
          date = new Date(timestamp)
        } else if (typeof timestamp === 'number' || (typeof timestamp === 'string' && /^\d+$/.test(timestamp))) {
          const num = typeof timestamp === 'string' ? parseInt(timestamp, 10) : timestamp
          date = new Date(num < 1e12 ? num * 1000 : num)
        } else {
          return '-'
        }
        if (isNaN(date.getTime())) return '-'
        return date.toLocaleString()
      } catch (e) {
        return '-'
      }
    },
    getTypeClass (type) {
      if (!type) return ''
      const t = type.toLowerCase()
      if (t.includes('open_long') || t.includes('add_long')) return 'long'
      if (t.includes('open_short') || t.includes('add_short')) return 'short'
      if (t.includes('close_long')) return 'close-long'
      if (t.includes('close_short')) return 'close-short'
      return ''
    },
    getSignalTypeText (type) {
      if (!type) return '-'
      const map = {
        'open_long': this.$t('broker.signal.openLong'),
        'open_short': this.$t('broker.signal.openShort'),
        'close_long': this.$t('broker.signal.closeLong'),
        'close_short': this.$t('broker.signal.closeShort'),
        'add_long': this.$t('broker.signal.addLong'),
        'add_short': this.$t('broker.signal.addShort')
      }
      return map[type.toLowerCase()] || type.toUpperCase()
    },
    getStatusText (status) {
      if (!status) return '-'
      const map = {
        'pending': this.$t('broker.status.pending'),
        'processing': this.$t('broker.status.processing'),
        'completed': this.$t('broker.status.completed'),
        'failed': this.$t('broker.status.failed'),
        'cancelled': this.$t('broker.status.cancelled')
      }
      return map[status.toLowerCase()] || status.toUpperCase()
    }
  }
}
</script>

<style lang="less" scoped>
@bg-dark: #0f172a;
@bg-card-dark: #1e293b;
@border-dark: #334155;
@text-primary-dark: #f1f5f9;
@text-secondary-dark: #94a3b8;

@bg-light: #f8fafc;
@bg-card-light: #ffffff;
@border-light: #e2e8f0;
@text-primary-light: #1e293b;
@text-secondary-light: #64748b;

@green: #10b981;
@green-light: #34d399;
@red: #ef4444;
@red-light: #f87171;
@blue: #3b82f6;
@purple: #8b5cf6;
@amber: #f59e0b;
@cyan: #06b6d4;

.broker-dashboard {
  min-height: 100vh;
  padding: 20px;
  background: @bg-light;
  transition: background 0.3s;

  &.theme-dark {
    background: @bg-dark;

    .connection-bar {
      background: @bg-card-dark;
      border-color: @border-dark;
      .conn-label, .conn-account { color: @text-primary-dark; }
    }

    .kpi-card {
      background: @bg-card-dark;
      border-color: @border-dark;
      .kpi-label { color: @text-secondary-dark; }
      .kpi-value .amount { color: @text-primary-dark; }
      .kpi-sub { color: @text-secondary-dark; }
    }

    .chart-panel {
      background: @bg-card-dark;
      border-color: @border-dark;
      .panel-header {
        border-color: @border-dark;
        .panel-title { color: @text-primary-dark; }
      }
    }

    .pro-table {
      ::v-deep .ant-table {
        background: transparent;
        color: @text-primary-dark;
      }
      ::v-deep .ant-table-thead > tr > th {
        background: rgba(51, 65, 85, 0.5);
        color: @text-secondary-dark;
        border-color: @border-dark;
      }
      ::v-deep .ant-table-tbody > tr > td {
        border-color: @border-dark;
        color: @text-primary-dark;
      }
      ::v-deep .ant-table-tbody > tr:hover > td {
        background: rgba(51, 65, 85, 0.3);
      }
      ::v-deep .ant-table-placeholder {
        background: transparent;
        .ant-empty-description { color: @text-secondary-dark; }
      }
      ::v-deep .ant-pagination {
        .ant-pagination-item {
          background: @bg-card-dark;
          border-color: @border-dark;
          a { color: @text-primary-dark; }
          &.ant-pagination-item-active {
            background: @blue;
            border-color: @blue;
          }
        }
        .ant-pagination-prev, .ant-pagination-next {
          .ant-pagination-item-link {
            background: @bg-card-dark;
            border-color: @border-dark;
            color: @text-primary-dark;
          }
        }
      }
    }
  }

  // Connection bar
  .connection-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    border-radius: 12px;
    margin-bottom: 20px;
    background: @bg-card-light;
    border: 1px solid @border-light;
    transition: all 0.3s;

    &.connected {
      border-left: 4px solid @green;
      .conn-dot { background: @green; box-shadow: 0 0 8px @green; }
    }
    &.disconnected {
      border-left: 4px solid @red;
      .conn-dot { background: @red; box-shadow: 0 0 8px @red; }
    }

    .conn-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .conn-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      animation: pulse 2s infinite;
    }
    .conn-label {
      font-weight: 600;
      font-size: 14px;
    }
    .conn-account {
      font-size: 12px;
      color: @text-secondary-light;
      padding: 2px 8px;
      background: rgba(59, 130, 246, 0.1);
      border-radius: 4px;
    }
    .conn-right {
      display: flex;
      align-items: center;
    }
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  // KPI Grid
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 20px;
  }

  .kpi-card {
    position: relative;
    background: @bg-card-light;
    border: 1px solid @border-light;
    border-radius: 16px;
    padding: 20px;
    overflow: hidden;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
    }

    .kpi-glow {
      position: absolute;
      top: -50%; right: -50%;
      width: 100%; height: 100%;
      background: radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, transparent 70%);
      pointer-events: none;
    }
    .kpi-content { position: relative; z-index: 1; }
    .kpi-header {
      display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
    }
    .kpi-icon {
      width: 32px; height: 32px;
      display: flex; align-items: center; justify-content: center;
      border-radius: 8px;
      background: rgba(59, 130, 246, 0.1);
      color: @blue; font-size: 16px;
    }
    .kpi-label {
      font-size: 12px; font-weight: 600;
      color: @text-secondary-light;
      text-transform: uppercase; letter-spacing: 0.5px;
    }
    .kpi-value {
      display: flex; align-items: baseline; gap: 2px;
      .currency { font-size: 18px; font-weight: 500; color: @text-secondary-light; }
      .amount { font-size: 28px; font-weight: 700; color: @text-primary-light; font-feature-settings: 'tnum'; }
      .unit { font-size: 14px; font-weight: 500; color: @text-secondary-light; margin-left: 4px; }
    }
    .kpi-sub {
      margin-top: 8px; font-size: 12px; color: @text-secondary-light;
      .label { margin: 0 2px; }
      .divider { margin: 0 6px; opacity: 0.5; }
    }

    &.kpi-primary {
      background: linear-gradient(135deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
      border: none;
      .kpi-icon { background: rgba(255,255,255,0.2); color: #fff; }
      .kpi-label { color: rgba(255,255,255,0.8); }
      .kpi-value { .currency, .amount, .unit { color: #fff; } }
      .kpi-sub { color: rgba(255,255,255,0.7); }
    }

    &.kpi-win-rate {
      .kpi-ring {
        position: absolute; right: 12px; top: 50%;
        transform: translateY(-50%);
        width: 60px; height: 60px;
        svg {
          transform: rotate(-90deg);
          .ring-bg { fill: none; stroke: rgba(16,185,129,0.15); stroke-width: 3; }
          .ring-progress { fill: none; stroke: @green; stroke-width: 3; stroke-linecap: round; transition: stroke-dasharray 0.5s ease; }
        }
      }
      .kpi-icon { background: rgba(16,185,129,0.1); color: @green; }
    }
    &.kpi-profit-factor {
      .kpi-icon { background: rgba(139,92,246,0.1); color: @purple; }
    }
    &.kpi-trades {
      .kpi-icon { background: rgba(6,182,212,0.1); color: @cyan; }
    }
    &.kpi-cash {
      .kpi-icon { background: rgba(245,158,11,0.1); color: @amber; }
    }
    &.kpi-realized {
      .kpi-icon { background: rgba(16,185,129,0.1); color: @green; }
    }
  }

  // Panels
  .chart-panel {
    background: @bg-card-light;
    border: 1px solid @border-light;
    border-radius: 16px;
    overflow: hidden;
    margin-bottom: 16px;

    .panel-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 16px 20px;
      border-bottom: 1px solid @border-light;
    }
    .panel-title {
      display: flex; align-items: center; gap: 8px;
      font-size: 14px; font-weight: 600; color: @text-primary-light;
      .anticon { color: @blue; }
      .source-tag {
        font-size: 10px; font-weight: 500;
        color: @text-secondary-light;
        background: rgba(59,130,246,0.08);
        padding: 1px 6px; border-radius: 4px;
        letter-spacing: 0.3px;
      }
    }
    .panel-badge {
      background: @blue; color: #fff;
      font-size: 11px; font-weight: 600;
      padding: 2px 8px; border-radius: 10px;
    }
  }

  // Table styles
  .pro-table {
    ::v-deep .ant-table { font-size: 13px; }
    ::v-deep .ant-table-thead > tr > th {
      background: rgba(241,245,249,0.8);
      font-weight: 600; font-size: 12px;
      text-transform: uppercase; letter-spacing: 0.5px;
      color: @text-secondary-light;
      border-bottom: 1px solid @border-light;
      padding: 12px 16px;
    }
    ::v-deep .ant-table-tbody > tr > td {
      padding: 12px 16px;
      border-bottom: 1px solid @border-light;
    }
    ::v-deep .ant-table-tbody > tr:hover > td {
      background: rgba(59,130,246,0.04);
    }
    ::v-deep .ant-pagination {
      padding: 12px 16px; margin: 0;
    }
  }

  // Cell styles
  .symbol-cell {
    .symbol-name { font-weight: 600; display: block; }
    .symbol-strategy { font-size: 11px; color: @text-secondary-light; }
  }
  .side-tag {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600;
    &.long { background: rgba(16,185,129,0.1); color: @green; }
    &.short { background: rgba(239,68,68,0.1); color: @red; }
  }
  .type-tag {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600;
    &.long { background: rgba(16,185,129,0.1); color: @green; }
    &.short { background: rgba(239,68,68,0.1); color: @red; }
    &.close-long { background: rgba(245,158,11,0.1); color: @amber; }
    &.close-short { background: rgba(139,92,246,0.1); color: @purple; }
  }
  .symbol-tag {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600;
    background: rgba(59,130,246,0.1); color: @blue;
  }
  .status-tag {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600;
    &.pending, &.presubmitted { background: rgba(245,158,11,0.1); color: @amber; }
    &.processing, &.submitted { background: rgba(59,130,246,0.1); color: @blue; }
    &.completed, &.filled { background: rgba(16,185,129,0.1); color: @green; }
    &.failed, &.inactive, &.cancelled, &.apicancelled { background: rgba(239,68,68,0.1); color: @red; }
  }
  .error-hint {
    font-size: 11px;
    color: @red;
    margin-top: 4px;
    cursor: pointer;
    .anticon { margin-right: 4px; }
  }
  .progress-bar-wrap {
    height: 4px; background: rgba(0,0,0,0.06); border-radius: 2px; margin-top: 4px;
    .progress-bar-fill {
      height: 100%; border-radius: 2px;
      background: linear-gradient(90deg, @blue, @cyan);
      transition: width 0.3s;
    }
  }
  .time-cell { font-size: 12px; color: @text-secondary-light; }
  .sub-text { font-size: 11px; color: @text-secondary-light; }
  .text-muted { color: @text-secondary-light; }
  .positive { color: @green; }
  .negative { color: @red; }

  @media (max-width: 768px) {
    padding: 12px;
    .kpi-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .kpi-card {
      padding: 14px;
      .kpi-value .amount { font-size: 22px; }
      &.kpi-win-rate .kpi-ring { width: 48px; height: 48px; right: 8px; }
    }
  }
}
</style>
