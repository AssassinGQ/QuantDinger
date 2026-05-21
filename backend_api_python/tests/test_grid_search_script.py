"""Tests for Phase 23 grid search research script."""
import pytest
import yaml
import json
import os
import tempfile
import sys
import math
import pandas as pd
from unittest.mock import patch, MagicMock

# Add scripts directory to path for imports
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, SCRIPTS_DIR)


class TestConfigParsing:
    """Test cases for YAML config parsing."""

    def test_config_parsing_valid_yaml(self):
        """Test that a valid YAML config file parses correctly."""
        from scripts.cross_sectional.grid_search import load_config

        config_path = os.path.join(SCRIPTS_DIR, "scripts/cross_sectional/test_grid_config.yaml")
        config = load_config(config_path)

        assert 'search_space' in config
        assert config['search_space']['factors'] == ['MOM_1M', 'MOM_3M', 'VOL_20D', 'SHARPE_60D']
        assert config['search_space']['combo_min'] == 1
        assert config['search_space']['combo_max'] == 2
        assert config['search_space']['n_long_options'] == [10, 20]

    def test_config_missing_file(self):
        """Test missing config file raises FileNotFoundError."""
        from scripts.cross_sectional.grid_search import load_config

        with pytest.raises(FileNotFoundError) as exc:
            load_config("nonexistent.yaml")
        assert "Config file not found" in str(exc.value)

    def test_config_invalid_yaml(self):
        """Test invalid YAML raises YAMLError."""
        from scripts.cross_sectional.grid_search import load_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("factors: [invalid syntax\n")  # Unbalanced bracket
            bad_path = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                load_config(bad_path)
        finally:
            os.unlink(bad_path)

    def test_config_missing_required_field(self):
        """Test config missing required field raises ValueError."""
        from scripts.cross_sectional.grid_search import load_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("search_space:\n  combo_min: 1\n")  # Missing factors
            bad_path = f.name

        try:
            with pytest.raises(ValueError) as exc:
                load_config(bad_path)
            assert "factors" in str(exc.value)
        finally:
            os.unlink(bad_path)


class TestFactorCombination:
    """Test cases for factor combination generation."""

    def test_factor_combination_generation(self):
        """Test that factor combinations are generated correctly."""
        from scripts.cross_sectional.grid_search import generate_factor_combinations

        factors = ['A', 'B', 'C']
        combos = generate_factor_combinations(factors, combo_min=1, combo_max=2)

        # Expected: C(3,1)=3 single factors + C(3,2)=3 pairs = 6 total
        assert len(combos) == 6

        # Check structure
        for combo in combos:
            assert 'factors' in combo
            assert 'directions' in combo
            assert isinstance(combo['factors'], list)
            assert isinstance(combo['directions'], list)

    def test_combo_size_coverage(self):
        """Test all combo sizes from min to max are generated."""
        from scripts.cross_sectional.grid_search import generate_factor_combinations

        factors = ['A', 'B', 'C', 'D']
        combos = generate_factor_combinations(factors, combo_min=1, combo_max=3)

        sizes = [len(c['factors']) for c in combos]
        assert 1 in sizes
        assert 2 in sizes
        assert 3 in sizes
        assert 4 not in sizes  # combo_max=3, so size 4 not included
        assert len(combos) == 14  # C(4,1)+C(4,2)+C(4,3) = 4+6+4

    def test_combo_structure_with_directions(self):
        """Test each combo has correct factors and directions."""
        from scripts.cross_sectional.grid_search import generate_factor_combinations

        factors = ['MOM_1M', 'VOL_20D']  # Known directions: +1, -1
        combos = generate_factor_combinations(factors, combo_min=2, combo_max=2)

        assert len(combos) == 1
        assert combos[0]['factors'] == ['MOM_1M', 'VOL_20D']
        assert combos[0]['directions'] == [1, -1]

    def test_full_combo_count(self):
        """Test total count matches mathematical expectation."""
        from scripts.cross_sectional.grid_search import generate_factor_combinations

        factors = ['A', 'B', 'C', 'D', 'E']
        combos = generate_factor_combinations(factors, combo_min=1, combo_max=4)

        # C(5,1) + C(5,2) + C(5,3) + C(5,4)
        expected = sum(math.comb(5, k) for k in range(1, 5))
        assert len(combos) == expected  # 5+10+10+5 = 30


class TestCliParsing:
    """Test cases for CLI argument parsing."""

    def test_cli_default_config(self):
        """Test default config path is grid_config.yaml."""
        from scripts.cross_sectional.grid_search import parse_args

        # Simulate no arguments
        old_argv = sys.argv
        sys.argv = ['grid_search.py']
        try:
            args = parse_args()
            assert args.config == "grid_config.yaml"
        finally:
            sys.argv = old_argv

    def test_cli_custom_config(self):
        """Test CLI accepts custom config path."""
        from scripts.cross_sectional.grid_search import parse_args

        old_argv = sys.argv
        sys.argv = ['grid_search.py', '--config', 'custom.yaml']
        try:
            args = parse_args()
            assert args.config == "custom.yaml"
        finally:
            sys.argv = old_argv

    def test_cli_base_url(self):
        """Test CLI accepts base-url argument."""
        from scripts.cross_sectional.grid_search import parse_args

        old_argv = sys.argv
        sys.argv = ['grid_search.py', '--base-url', 'http://test:5000']
        try:
            args = parse_args()
            assert args.base_url == "http://test:5000"
        finally:
            sys.argv = old_argv

    def test_cli_token_auth(self):
        """Test CLI accepts token argument."""
        from scripts.cross_sectional.grid_search import parse_args

        old_argv = sys.argv
        sys.argv = ['grid_search.py', '--token', 'mytoken123']
        try:
            args = parse_args()
            assert args.token == "mytoken123"
        finally:
            sys.argv = old_argv


class TestApiIntegration:
    """Test cases for Phase 22 HTTP API integration."""

    def test_api_call_success(self):
        """Test successful API call returns data dict."""
        from scripts.cross_sectional.grid_search import call_phase22_backtest
        import requests

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 1,
            "msg": "OK",
            "data": {
                "neutral_off": {"summary": {"annualReturn": 15.0}},
                "neutral_on": {"summary": {"annualReturn": 12.0}},
            }
        }

        with patch('requests.post', return_value=mock_response):
            result = call_phase22_backtest(
                "http://test", "token", "nq100",
                "2021-01-01", "2022-01-01", "code", 20
            )
            assert result is not None
            assert "neutral_off" in result
            assert "neutral_on" in result

    def test_api_error_handling(self):
        """Test API returns code=0, function returns None."""
        from scripts.cross_sectional.grid_search import call_phase22_backtest

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "msg": "BT01_POOL: validation error",
            "data": None
        }

        with patch('requests.post', return_value=mock_response):
            result = call_phase22_backtest(
                "http://test", "token", "nq100",
                "2021-01-01", "2022-01-01", "code", 20
            )
            assert result is None

    def test_timeout_retry(self):
        """Test timeout triggers retry, succeeds on second attempt."""
        from scripts.cross_sectional.grid_search import call_phase22_backtest
        import requests

        mock_success = MagicMock()
        mock_success.json.return_value = {"code": 1, "msg": "OK", "data": {"neutral_off": {}}}

        call_count = [0]
        def mock_post(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise requests.Timeout()
            return mock_success

        with patch('requests.post', side_effect=mock_post):
            result = call_phase22_backtest(
                "http://test", "token", "nq100",
                "2021-01-01", "2022-01-01", "code", 20
            )
            assert result is not None
            assert call_count[0] == 2  # First timeout, second success

    def test_login_success(self):
        """Test login returns token on success."""
        from scripts.cross_sectional.grid_search import login

        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 1, "data": {"token": "mytoken"}}

        with patch('requests.post', return_value=mock_response):
            token = login("http://test", "user", "pass")
            assert token == "mytoken"


class TestIndicatorCodeBuilder:
    """Test cases for indicator code builder."""

    def test_indicator_single_factor(self):
        """Test single factor generates valid indicator code."""
        from scripts.cross_sectional.grid_search import build_indicator_code

        code = build_indicator_code(['MOM_1M'], [1])

        assert "compute_factor_by_name('MOM_1M'" in code
        assert "scores[s]" in code
        assert "weights[s]" in code

    def test_indicator_multi_factor(self):
        """Test multi-factor generates weighted composite."""
        from scripts.cross_sectional.grid_search import build_indicator_code

        code = build_indicator_code(['MOM_1M', 'VOL_20D'], [1, -1])

        assert "compute_factor_by_name('MOM_1M'" in code
        assert "compute_factor_by_name('VOL_20D'" in code
        assert "composite" in code
        assert "0.5" in code  # Weight for 2 factors

    def test_indicator_weights_assignment(self):
        """Test indicator code assigns weights to top N."""
        from scripts.cross_sectional.grid_search import build_indicator_code

        code = build_indicator_code(['MOM_1M'], [1])

        assert "weights[s] = 1.0 / n_long" in code
        assert "sorted_symbols" in code

    def test_indicator_phase20_import(self):
        """Test indicator imports Phase 20 factor library."""
        from scripts.cross_sectional.grid_search import build_indicator_code

        code = build_indicator_code(['SHARPE_60D'], [1])

        assert "from app.factors.factor_defs import compute_factor_by_name" in code


class TestScoreCalculation:
    """Test cases for score calculation."""

    def test_score_valid_summary(self):
        """Test valid summary produces correct score."""
        from scripts.cross_sectional.grid_search import compute_score

        summary = {
            "annualReturn": 20.0,
            "sharpeRatio": 1.5,
            "maxDrawdown": -15.0,
            "calmarRatio": 1.3,
            "winRate": 60.0,
        }

        score = compute_score(summary)

        # 20*0.25 + 1.5*10*0.30 + min(1.3,5)*5*0.15 - 15*0.15 + min(60,70)*0.15
        expected = 5.0 + 4.5 + 0.975 - 2.25 + 9.0
        assert abs(score - expected) < 0.01

    def test_score_none_summary(self):
        """Test None summary returns -9999."""
        from scripts.cross_sectional.grid_search import compute_score

        assert compute_score(None) == -9999.0

    def test_score_formula_weights(self):
        """Test score uses correct formula weights."""
        from scripts.cross_sectional.grid_search import compute_score

        # Test each component independently
        # Annual: 10% * 0.25 = 2.5
        assert compute_score({"annualReturn": 10.0}) == 2.5 - 15.0  # MaxDD default -100

        # Sharpe: 1.0 * 10 * 0.30 = 3.0
        assert compute_score({"sharpeRatio": 1.0}) == 3.0 - 15.0  # MaxDD default

        # Calmar: min(3, 5) * 5 * 0.15 = 2.25
        assert compute_score({"calmarRatio": 3.0}) == 2.25 - 15.0

    def test_score_missing_fields(self):
        """Test missing fields handled gracefully."""
        from scripts.cross_sectional.grid_search import compute_score

        summary = {"annualReturn": 10.0}  # Missing sharpe, maxDD, calmar, winRate

        score = compute_score(summary)
        # 10*0.25 + 0 + 0 - 100*0.15 + 0 = 2.5 - 15 = -12.5
        assert score == -12.5

    def test_score_caps(self):
        """Test Calmar and WinRate caps."""
        from scripts.cross_sectional.grid_search import compute_score

        # Calmar capped at 5
        high_calmar = compute_score({"calmarRatio": 10.0})
        capped_calmar = compute_score({"calmarRatio": 5.0})
        assert high_calmar == capped_calmar  # Both capped at 5

        # WinRate capped at 70
        high_win = compute_score({"winRate": 80.0})
        capped_win = compute_score({"winRate": 70.0})
        assert high_win == capped_win  # Both capped at 70


class TestCheckpoint:
    """Test cases for checkpoint resume logic."""

    def test_checkpoint_load_missing(self):
        """Test load_checkpoint returns empty for missing file."""
        from scripts.cross_sectional.grid_search import load_checkpoint

        done, results = load_checkpoint("/nonexistent/checkpoint.json")
        assert done == set()
        assert results == []

    def test_checkpoint_load_existing(self):
        """Test load_checkpoint parses existing file."""
        from scripts.cross_sectional.grid_search import load_checkpoint

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"done": ["MOM_1M|10|w1", "VOL_20D|20|w1"]}, f)
            ckpt_path = f.name

        try:
            done, results = load_checkpoint(ckpt_path)
            assert "MOM_1M|10|w1" in done
            assert "VOL_20D|20|w1" in done
            assert len(done) == 2
        finally:
            os.unlink(ckpt_path)

    def test_checkpoint_save(self):
        """Test save_checkpoint writes valid JSON."""
        from scripts.cross_sectional.grid_search import save_checkpoint, load_checkpoint

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            ckpt_path = f.name

        try:
            save_checkpoint(ckpt_path, {"A|10|w1"}, [{"factors": ["A"], "n_long": 10}])

            # Verify by loading
            done, results = load_checkpoint(ckpt_path)
            assert "A|10|w1" in done
            assert len(results) == 1
        finally:
            os.unlink(ckpt_path)

    def test_checkpoint_key_format(self):
        """Test checkpoint key format."""
        from scripts.cross_sectional.grid_search import make_checkpoint_key

        key1 = make_checkpoint_key(['MOM_1M', 'VOL_20D'], 15, window_id=2)
        assert key1 == "MOM_1M+VOL_20D|15|w2"

        key2 = make_checkpoint_key(['SHARPE_60D'], 20, window_id=None)
        assert key2 == "SHARPE_60D|20"


class TestJsonlOutput:
    """Test cases for JSONL output."""

    def test_jsonl_append(self):
        """Test that JSONL append creates valid output."""
        from scripts.cross_sectional.grid_search import append_result_jsonl

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            jsonl_path = f.name

        try:
            result = {'factors': ['MOM_1M'], 'n_long': 10, 'score': 5.5}
            append_result_jsonl(jsonl_path, result)

            # Read and verify
            with open(jsonl_path) as f:
                line = f.readline()
                parsed = json.loads(line)
                assert parsed['factors'] == ['MOM_1M']
                assert parsed['score'] == 5.5
        finally:
            os.unlink(jsonl_path)

    def test_jsonl_accumulates(self):
        """Test multiple append calls produce multiple lines."""
        from scripts.cross_sectional.grid_search import append_result_jsonl

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            jsonl_path = f.name

        try:
            for i in range(3):
                append_result_jsonl(jsonl_path, {'idx': i, 'score': i * 10})

            with open(jsonl_path) as f:
                lines = f.readlines()
                assert len(lines) == 3
                for line in lines:
                    json.loads(line)  # Verify each parseable
        finally:
            os.unlink(jsonl_path)


class TestCsvOutput:
    """Test cases for CSV output."""

    def test_csv_export_columns(self):
        """Test CSV export has correct columns per D-15."""
        from scripts.cross_sectional.grid_search import export_results_csv

        results = [
            {
                'factors': ['MOM_1M'],
                'n_long': 10,
                'neutral_off_summary': {'annualReturn': 15, 'sharpeRatio': 1.5},
                'neutral_off_score': 10.0,
            }
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            csv_path = f.name

        try:
            export_results_csv(results, csv_path, neutral_mode='off')

            df = pd.read_csv(csv_path)
            expected_cols = ['factors', 'n_long', 'annualReturn', 'sharpeRatio',
                            'calmarRatio', 'maxDrawdown', 'winRate', 'totalMonths', 'score', 'window_id']
            for col in expected_cols:
                assert col in df.columns
        finally:
            os.unlink(csv_path)

    def test_csv_valid_parse(self):
        """Test CSV can be parsed with correct row count."""
        from scripts.cross_sectional.grid_search import export_results_csv

        results = [
            {'factors': ['A'], 'n_long': 10, 'neutral_off_summary': {}, 'neutral_off_score': 1},
            {'factors': ['B'], 'n_long': 20, 'neutral_off_summary': {}, 'neutral_off_score': 2},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            csv_path = f.name

        try:
            export_results_csv(results, csv_path)

            df = pd.read_csv(csv_path)
            assert len(df) == 2
        finally:
            os.unlink(csv_path)


class TestHtmlOutput:
    """Test cases for HTML output."""

    def test_html_config_summary(self):
        """Test HTML contains config summary."""
        from scripts.cross_sectional.grid_search import generate_html_report

        config = {
            'search_space': {
                'factors': ['A', 'B', 'C'],
                'combo_min': 1,
                'combo_max': 2,
                'n_long_options': [10, 20],
            },
            'walk_forward': {'enabled': False},
        }
        results = [{'factors': ['A'], 'n_long': 10, 'neutral_off_score': 5, 'neutral_off_summary': {}}]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            html_path = f.name

        try:
            generate_html_report(results, config, html_path, neutral_mode='off')

            with open(html_path) as f:
                html = f.read()
                assert "Factors: 3 available" in html
                assert "Combo sizes: 1 to 2" in html
        finally:
            os.unlink(html_path)

    def test_html_top20_table(self):
        """Test HTML contains TOP 20 table."""
        from scripts.cross_sectional.grid_search import generate_html_report

        config = {'search_space': {'factors': ['A'], 'combo_min': 1, 'combo_max': 1, 'n_long_options': [10]}}
        results = [
            {'factors': ['A'], 'n_long': 10, 'neutral_off_score': i, 'neutral_off_summary': {'annualReturn': i}}
            for i in range(25)
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            html_path = f.name

        try:
            generate_html_report(results, config, html_path)

            with open(html_path) as f:
                html = f.read()
                assert "Top 20 Results" in html
                assert "<tr>" in html  # Table rows exist
        finally:
            os.unlink(html_path)

    def test_html_factor_frequency(self):
        """Test HTML contains factor frequency table."""
        from scripts.cross_sectional.grid_search import generate_html_report

        config = {'search_space': {'factors': ['A', 'B'], 'combo_min': 1, 'combo_max': 1, 'n_long_options': [10]}}
        results = [
            {'factors': ['A'], 'n_long': 10, 'neutral_off_score': 10, 'neutral_off_summary': {}},
            {'factors': ['A'], 'n_long': 10, 'neutral_off_score': 9, 'neutral_off_summary': {}},
            {'factors': ['B'], 'n_long': 10, 'neutral_off_score': 8, 'neutral_off_summary': {}},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            html_path = f.name

        try:
            generate_html_report(results, config, html_path)

            with open(html_path) as f:
                html = f.read()
                assert "Factor Frequency" in html
                assert "Appearances" in html
        finally:
            os.unlink(html_path)

    def test_html_valid_structure(self):
        """Test HTML has valid structure."""
        from scripts.cross_sectional.grid_search import generate_html_report

        config = {'search_space': {'factors': ['A'], 'combo_min': 1, 'combo_max': 1, 'n_long_options': [10]}}
        results = [{'factors': ['A'], 'n_long': 10, 'neutral_off_score': 1, 'neutral_off_summary': {}}]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            html_path = f.name

        try:
            generate_html_report(results, config, html_path)

            with open(html_path) as f:
                html = f.read()
                assert "<!DOCTYPE html>" in html
                assert "<html>" in html
                assert "</html>" in html
                assert "<body>" in html
        finally:
            os.unlink(html_path)


class TestWalkForward:
    """Test cases for walk-forward window generation."""

    def test_walk_forward_window_count(self):
        """Test correct number of windows generated."""
        from scripts.cross_sectional.grid_search import generate_walk_forward_windows

        windows = generate_walk_forward_windows(
            start_date='2020-01-01',
            end_date='2026-01-01',
            train_months=36,
            test_months=12,
            step_months=12,
        )

        # Should generate at least 1 window
        assert len(windows) >= 1

    def test_walk_forward_window_fields(self):
        """Test each window has required fields."""
        from scripts.cross_sectional.grid_search import generate_walk_forward_windows

        windows = generate_walk_forward_windows('2020-01-01', '2025-01-01', 12, 6, 6)

        for w in windows:
            assert 'window_id' in w
            assert 'train_start' in w
            assert 'train_end' in w
            assert 'test_start' in w
            assert 'test_end' in w

    def test_walk_forward_no_overlap(self):
        """Test train and test periods don't overlap."""
        from scripts.cross_sectional.grid_search import generate_walk_forward_windows

        windows = generate_walk_forward_windows('2020-01-01', '2025-01-01', 24, 12, 12)

        for w in windows:
            # train_end should equal test_start (no overlap, no gap)
            assert w['train_end'] == w['test_start']

    def test_walk_forward_slide(self):
        """Test windows slide by step_months."""
        from scripts.cross_sectional.grid_search import generate_walk_forward_windows
        from datetime import datetime

        windows = generate_walk_forward_windows('2020-01-01', '2025-01-01', 12, 6, 12)

        if len(windows) >= 2:
            # Window 2 train_start should be ~12 months after Window 1 train_start
            w1_start = datetime.strptime(windows[0]['train_start'], '%Y-%m-%d')
            w2_start = datetime.strptime(windows[1]['train_start'], '%Y-%m-%d')

            # Approximate: 12 months ~ 360 days
            diff_days = (w2_start - w1_start).days
            assert 350 <= diff_days <= 370  # Allow ~30-day variance for month length

    def test_oos_extraction(self):
        """Test aggregate_oos_results extracts test phase only."""
        from scripts.cross_sectional.grid_search import aggregate_oos_results

        results = [
            {'phase': 'train', 'window_id': 1},
            {'phase': 'test', 'oos': True, 'window_id': 1},
            {'phase': 'train', 'window_id': 2},
        ]

        oos = aggregate_oos_results(results)
        assert len(oos) == 1
        assert oos[0]['phase'] == 'test'

    def test_oos_summary_stats(self):
        """Test OOS aggregation computes average stats."""
        from scripts.cross_sectional.grid_search import compute_oos_summary

        oos_results = [
            {'neutral_off_summary': {'sharpeRatio': 1.0, 'annualReturn': 10}, 'neutral_off_score': 5},
            {'neutral_off_summary': {'sharpeRatio': 2.0, 'annualReturn': 20}, 'neutral_off_score': 10},
        ]

        summary = compute_oos_summary(oos_results)
        assert summary['avg_sharpe'] == 1.5
        assert summary['avg_annual_return'] == 15.0
        assert summary['avg_score'] == 7.5
        assert summary['window_count'] == 2

    def test_oos_empty_results(self):
        """Test OOS summary for empty results."""
        from scripts.cross_sectional.grid_search import compute_oos_summary

        summary = compute_oos_summary([])
        assert summary['avg_sharpe'] == 0
        assert summary['avg_annual_return'] == 0
        assert summary['avg_score'] == -9999
        assert summary['window_count'] == 0

    def test_dual_top100_outputs(self):
        """Test save_top100_outputs creates both files."""
        from scripts.cross_sectional.grid_search import save_top100_outputs
        import tempfile

        results = [
            {'factors': ['A'], 'n_long': 10, 'neutral_off_score': 10, 'neutral_on_score': 8,
             'neutral_off_summary': {'annualReturn': 15}, 'neutral_on_summary': {'annualReturn': 12}},
            {'factors': ['B'], 'n_long': 20, 'neutral_off_score': 5, 'neutral_on_score': 12,
             'neutral_off_summary': {}, 'neutral_on_summary': {}},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            save_top100_outputs(results, tmpdir)

            assert os.path.exists(os.path.join(tmpdir, 'neutral_off_top100.json'))
            assert os.path.exists(os.path.join(tmpdir, 'neutral_on_top100.json'))

    def test_top100_structure(self):
        """Test TOP 100 files have correct structure."""
        from scripts.cross_sectional.grid_search import save_top100_outputs
        import tempfile

        results = [
            {'factors': ['MOM_1M'], 'n_long': 10, 'neutral_off_score': 10, 'neutral_on_score': 8,
             'neutral_off_summary': {}, 'neutral_on_summary': {}},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            save_top100_outputs(results, tmpdir)

            with open(os.path.join(tmpdir, 'neutral_off_top100.json')) as f:
                data = json.load(f)
                assert isinstance(data, list)
                if data:
                    assert 'factors' in data[0]
                    assert 'n_long' in data[0]
                    assert 'score' in data[0]

    def test_grid_search_window_phase(self):
        """Test results have window_id and phase fields."""
        from scripts.cross_sectional.grid_search import run_walk_forward_grid_search

        # Simplified test with mocked API
        config = {
            'search_space': {'factors': ['MOM_1M'], 'combo_min': 1, 'combo_max': 1, 'n_long_options': [10]},
            'walk_forward': {'enabled': False},
            'backtest_defaults': {'start_date': '2021-01-01', 'end_date': '2022-01-01'},
            'output': {'progress_interval': 1},
        }

        # Mock API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 1,
            "msg": "OK",
            "data": {
                "neutral_off": {"summary": {"annualReturn": 10.0}},
                "neutral_on": {"summary": {"annualReturn": 8.0}},
            }
        }

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('requests.post', return_value=mock_response):
                results = run_walk_forward_grid_search(
                    "http://test", "token", config, tmpdir
                )

            if results:
                assert 'window_id' in results[0]
                assert 'phase' in results[0]