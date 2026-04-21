# -*- coding: utf-8 -*-
"""
Tiingo 限流优化 - ForexDataSource 单元测试
"""
import unittest
import os
from unittest.mock import patch, MagicMock

# 设置环境变量
os.environ['TIINGO_API_KEY'] = 'test_api_key'

from app.data_sources.forex import ForexDataSource, _forex_cache, _forex_prev_close_fallback


class TestForexDataSource(unittest.TestCase):
    """ForexDataSource 单元测试"""

    def setUp(self):
        """每个测试前清空缓存"""
        _forex_cache.clear()
        _forex_prev_close_fallback.clear()

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.forex._forex_resolve_prev_close', return_value=0.0)
    def test_get_ticker_returns_price(self, mock_prev, mock_get):
        """TC-01: 验证 get_ticker 返回实时价格"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'bidPrice': 31.50,
            'askPrice': 31.55,
            'midPrice': 31.525
        }]
        mock_get.return_value = mock_response

        forex = ForexDataSource()
        result = forex.get_ticker("XAGUSD")

        self.assertGreater(result['last'], 0)
        self.assertIn('bid', result)
        self.assertIn('ask', result)
        self.assertEqual(result['bid'], 31.50)
        self.assertEqual(result['ask'], 31.55)

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.forex._forex_resolve_prev_close', return_value=31.30)
    def test_get_ticker_uses_prev_close(self, mock_prev, mock_get):
        """TC-02: 验证涨跌使用库解析的昨日收盘"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'bidPrice': 31.50,
            'askPrice': 31.55,
            'midPrice': 31.525
        }]
        mock_get.return_value = mock_response

        forex = ForexDataSource()
        result = forex.get_ticker("XAGUSD")

        self.assertEqual(result['previousClose'], 31.30)
        self.assertEqual(result['previousCloseSource'], 'kline')
        self.assertAlmostEqual(result['change'], 0.225, places=3)
        self.assertAlmostEqual(result['changePercent'], 0.72, places=1)

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.forex._forex_resolve_prev_close', return_value=0.0)
    def test_get_ticker_fallback_when_no_prev_close(self, mock_prev, mock_get):
        """TC-03: 无昨日收盘时涨跌为 0"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'bidPrice': 31.50,
            'askPrice': 31.55,
            'midPrice': 31.525
        }]
        mock_get.return_value = mock_response

        forex = ForexDataSource()
        result = forex.get_ticker("XAGUSD")

        self.assertGreater(result['last'], 0)
        self.assertEqual(result['change'], 0)
        self.assertEqual(result['changePercent'], 0)

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.forex._forex_resolve_prev_close', return_value=31.30)
    def test_get_ticker_cache_mechanism(self, mock_prev, mock_get):
        """TC-04: 验证 60 秒内重复调用命中缓存"""
        _forex_cache.clear()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'bidPrice': 31.50,
            'askPrice': 31.55,
            'midPrice': 31.525
        }]
        mock_get.return_value = mock_response

        forex = ForexDataSource()

        result1 = forex.get_ticker("XAGUSD")
        first_call_count = mock_get.call_count

        result2 = forex.get_ticker("XAGUSD")
        second_call_count = mock_get.call_count

        self.assertEqual(first_call_count, second_call_count)
        self.assertEqual(result1['last'], result2['last'])

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.forex._forex_resolve_prev_close', return_value=31.30)
    def test_prev_close_memory_fallback_after_resolve_zero(self, mock_prev, mock_get):
        """resolve 为 0 时可用内存兜底（先成功写入过内存）"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'bidPrice': 31.50,
            'askPrice': 31.55,
            'midPrice': 31.525,
        }]
        mock_get.return_value = mock_response

        forex = ForexDataSource()
        forex.get_ticker("XAGUSD")

        _forex_cache.clear()
        mock_prev.return_value = 0.0
        result = forex.get_ticker("XAGUSD")

        self.assertEqual(result['previousClose'], 31.30)
        self.assertEqual(result['previousCloseSource'], 'memory')
        self.assertAlmostEqual(result['change'], 0.225, places=3)


class TestForexDataSourceIntegration(unittest.TestCase):
    """ForexDataSource 集成测试"""

    def setUp(self):
        _forex_cache.clear()
        _forex_prev_close_fallback.clear()

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.forex._forex_resolve_prev_close')
    def test_change_consistency_with_prev_close(self, mock_prev, mock_get):
        """TC-06: 涨跌与昨日收盘一致"""
        yesterday_close = 31.30
        current_price = 31.525
        mock_prev.return_value = yesterday_close

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'bidPrice': 31.50,
            'askPrice': 31.55,
            'midPrice': current_price
        }]
        mock_get.return_value = mock_response

        forex = ForexDataSource()
        result = forex.get_ticker("XAGUSD")

        expected_change = current_price - yesterday_close
        expected_pct = (expected_change / yesterday_close) * 100

        self.assertAlmostEqual(result['change'], expected_change, places=3)
        self.assertAlmostEqual(result['changePercent'], expected_pct, places=1)


if __name__ == '__main__':
    unittest.main()