# -*- coding: utf-8 -*-
"""
Tiingo 限流优化 - ForexDataSource 单元测试
"""
import unittest
import os
from unittest.mock import patch, MagicMock

# 设置环境变量
os.environ['TIINGO_API_KEY'] = 'test_api_key'

# 顶层导入
from app.data_sources.forex import ForexDataSource, _forex_cache
from app.data_sources import DataSourceFactory


class TestForexDataSource(unittest.TestCase):
    """ForexDataSource 单元测试"""

    def setUp(self):
        """每个测试前清空缓存"""
        _forex_cache.clear()

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.DataSourceFactory.get_kline')
    def test_get_ticker_returns_price(self, mock_get_kline, mock_get):
        """TC-01: 验证 get_ticker 返回实时价格"""
        # Mock Tiingo API 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'bidPrice': 31.50,
            'askPrice': 31.55,
            'midPrice': 31.525
        }]
        mock_get.return_value = mock_response

        # Mock K 线缓存（返回昨日收盘价）
        mock_get_kline.return_value = [
            {'close': 31.40},  # 今日
            {'close': 31.30}   # 昨日
        ]

        forex = ForexDataSource()
        result = forex.get_ticker("XAGUSD")

        # Assert
        self.assertGreater(result['last'], 0)
        self.assertIn('bid', result)
        self.assertIn('ask', result)
        self.assertEqual(result['bid'], 31.50)
        self.assertEqual(result['ask'], 31.55)

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.DataSourceFactory.get_kline')
    def test_get_ticker_uses_kline_cache(self, mock_get_kline, mock_get):
        """TC-02: 验证 get_ticker 从 K 线缓存获取昨日收盘价"""
        # Mock Tiingo API 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'bidPrice': 31.50,
            'askPrice': 31.55,
            'midPrice': 31.525
        }]
        mock_get.return_value = mock_response

        # Mock K 线缓存
        mock_get_kline.return_value = [
            {'close': 31.30},  # 索引 0: 昨日
            {'close': 31.40}   # 索引 1: 今日
        ]

        forex = ForexDataSource()
        result = forex.get_ticker("XAGUSD")

        # Assert
        self.assertEqual(result['previousClose'], 31.30)
        self.assertAlmostEqual(result['change'], 0.225, places=3)
        self.assertAlmostEqual(result['changePercent'], 0.72, places=1)

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.DataSourceFactory.get_kline')
    def test_get_ticker_fallback_when_kline_unavailable(self, mock_get_kline, mock_get):
        """TC-03: 验证 K 线缓存未命中时优雅降级"""
        # Mock Tiingo API 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'bidPrice': 31.50,
            'askPrice': 31.55,
            'midPrice': 31.525
        }]
        mock_get.return_value = mock_response

        # Mock K 线缓存为空（未命中）
        mock_get_kline.return_value = []

        forex = ForexDataSource()
        result = forex.get_ticker("XAGUSD")

        # Assert
        self.assertGreater(result['last'], 0)
        self.assertIn('change', result)
        self.assertIn('changePercent', result)
        self.assertEqual(result['change'], 0)
        self.assertEqual(result['changePercent'], 0)

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.DataSourceFactory.get_kline')
    def test_get_ticker_cache_mechanism(self, mock_get_kline, mock_get):
        """TC-04: 验证 60 秒内重复调用命中缓存"""
        # 清空缓存
        _forex_cache.clear()

        # Mock Tiingo API 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'bidPrice': 31.50,
            'askPrice': 31.55,
            'midPrice': 31.525
        }]
        mock_get.return_value = mock_response

        # Mock K 线
        mock_get_kline.return_value = [
            {'close': 31.30},
            {'close': 31.40}
        ]

        forex = ForexDataSource()

        # 第一次调用
        result1 = forex.get_ticker("XAGUSD")
        first_call_count = mock_get.call_count

        # 60 秒内第二次调用（应命中缓存）
        result2 = forex.get_ticker("XAGUSD")
        second_call_count = mock_get.call_count

        # Assert
        self.assertEqual(first_call_count, second_call_count)
        self.assertEqual(result1['last'], result2['last'])


class TestForexDataSourceIntegration(unittest.TestCase):
    """ForexDataSource 集成测试"""

    def setUp(self):
        """每个测试前清空缓存"""
        _forex_cache.clear()

    @patch('app.data_sources.forex.requests.get')
    @patch('app.data_sources.DataSourceFactory.get_kline')
    def test_change_consistency_with_kline(self, mock_get_kline, mock_get):
        """TC-06: 验证涨跌数据与 K 线数据一致"""
        yesterday_close = 31.30
        current_price = 31.525

        # Mock get_kline 返回 [昨日, 今日]
        mock_get_kline.return_value = [
            {'close': yesterday_close},  # 索引 0: 昨日
            {'close': 31.40}               # 索引 1: 今日
        ]

        # Mock Tiingo 实时价格
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

        # 验证
        expected_change = current_price - yesterday_close
        expected_pct = (expected_change / yesterday_close) * 100

        self.assertAlmostEqual(result['change'], expected_change, places=3)
        self.assertAlmostEqual(result['changePercent'], expected_pct, places=1)


if __name__ == '__main__':
    unittest.main()