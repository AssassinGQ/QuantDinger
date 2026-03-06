
import request from '@/utils/request'

const api = {
  dashboard: '/api/ibkr/dashboard',
  connect: '/api/ibkr/connect',
  disconnect: '/api/ibkr/disconnect'
}

export function getIbkrDashboard () {
  return request({
    url: api.dashboard,
    method: 'get'
  })
}

export function connectIbkr (data) {
  return request({
    url: api.connect,
    method: 'post',
    data
  })
}

export function disconnectIbkr () {
  return request({
    url: api.disconnect,
    method: 'post'
  })
}
