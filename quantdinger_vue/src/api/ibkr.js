import request from '@/utils/request'

const api = {
  dashboard: '/api/ibkr/dashboard',
  status: '/api/ibkr/status',
  statusAll: '/api/ibkr/status-all',
  connect: '/api/ibkr/connect',
  disconnect: '/api/ibkr/disconnect'
}

export function getIbkrStatus (brokerId = 'ibkr-paper') {
  return request({
    url: api.status,
    method: 'get',
    params: { broker_id: brokerId }
  })
}

export function getIbkrStatusAll () {
  return request({
    url: api.statusAll,
    method: 'get'
  })
}

export function getIbkrDashboard (brokerId = 'ibkr-paper') {
  return request({
    url: api.dashboard,
    method: 'get',
    params: { broker_id: brokerId }
  })
}

export function connectIbkr (data) {
  return request({
    url: api.connect,
    method: 'post',
    data
  })
}

export function disconnectIbkr (mode) {
  return request({
    url: api.disconnect,
    method: 'post',
    data: mode ? { mode } : {}
  })
}
