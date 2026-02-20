/**
 * Multi-Strategy / Regime Switch API
 */
import request from '@/utils/request'

const base = '/api/multi-strategy'

export function getSummary () {
  return request({ url: `${base}/summary`, method: 'get' })
}

export function getWeights () {
  return request({ url: `${base}/weights`, method: 'get' })
}

export function putWeights (weights) {
  return request({ url: `${base}/weights`, method: 'put', data: { weights } })
}

export function getRegime () {
  return request({ url: `${base}/regime`, method: 'get' })
}

export function getAllocation () {
  return request({ url: `${base}/allocation`, method: 'get' })
}

export function getPositions (symbol) {
  return request({ url: `${base}/positions`, method: 'get', params: symbol ? { symbol } : {} })
}

export function getCircuitBreaker () {
  return request({ url: `${base}/circuit-breaker`, method: 'get' })
}

export function resetCircuitBreaker () {
  return request({ url: `${base}/circuit-breaker/reset`, method: 'post' })
}

export function getConfig () {
  return request({ url: `${base}/config`, method: 'get' })
}

export function putConfig (data) {
  return request({ url: `${base}/config`, method: 'put', data })
}

export function verifyCustomRegimeCode (data) {
  return request({ url: `${base}/config/verify-custom-code`, method: 'post', data })
}

export function parseYamlConfig (file) {
  const formData = new FormData()
  formData.append('file', file)
  return request({
    url: `${base}/config/parse-yaml`,
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export function getHistory (params = {}) {
  return request({ url: `${base}/history`, method: 'get', params })
}
