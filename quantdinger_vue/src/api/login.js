import request from '@/utils/request'

// 登录相关请求超时（网络较慢时易超时，调大至 90s）
const LOGIN_TIMEOUT = 90000

const userApi = {
  Login: '/api/auth/login',
  Logout: '/api/auth/logout',
  UserInfo: '/api/auth/info',
  UserMenu: '/user/nav'
}

/**
 * login func
 * parameter: {
 *     username: '',
 *     password: '',
 *     remember_me: true,
 *     captcha: '12345'
 * }
 * @param parameter
 * @returns {*}
 */
export function login (parameter) {
  return request({
    url: userApi.Login,
    method: 'post',
    data: parameter,
    timeout: LOGIN_TIMEOUT
  })
}

export function getInfo () {
  return request({
    url: userApi.UserInfo,
    method: 'get',
    headers: {
      'Content-Type': 'application/json;charset=UTF-8'
    },
    timeout: LOGIN_TIMEOUT
  })
}

// Backward-compatible alias: some modules still call getUserInfo()
export function getUserInfo () {
  return getInfo()
}

export function logout () {
  return request({
    url: userApi.Logout,
    method: 'post',
    headers: {
      'Content-Type': 'application/json;charset=UTF-8'
    }
  })
}

export function getCurrentUserNav () {
  return request({
    url: userApi.UserMenu,
    method: 'get'
  })
}
