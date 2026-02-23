"""Tests for the roomnl GP model."""

import datetime as dt

import numpy as np
import polars as pl
import pytest

from pipeline.roomnl_model import (
    build_features,
    fill_missing_with_gp,
    fit_gp_with_calendar,
    predict_daily,
    trends_monthly_multiplier,
)


@pytest.fixture
def sample_data() -> pl.DataFrame:
    """Minimal realistic dataset for model testing."""
    rng = np.random.default_rng(42)
    dates = pl.date_range(dt.date(2024, 1, 1), dt.date(2025, 6, 30), interval="7d", eager=True)
    n = len(dates)
    base_reg = 1200 + 300 * np.sin(np.linspace(0, 2 * np.pi, n))
    noise = rng.normal(0, 100, n)
    reg_time = np.clip(base_reg + noise, 200, 2500).astype(int)

    return pl.DataFrame(
        {
            "contract_date": dates,
            "registration_time": reg_time,
        }
    )


class TestBuildFeatures:
    def test_output_columns(self, sample_data: pl.DataFrame):
        dates = sample_data.get_column("contract_date")
        feats = build_features(dates)

        expected_cols = {
            "contract_date",
            "sin1",
            "cos1",
            "sin2",
            "cos2",
            "pre_sep",
            "pre_feb",
            "exam_jan",
            "exam_jun",
            "is_summer",
            "is_winter",
        }
        assert set(feats.columns) == expected_cols

    def test_output_length(self, sample_data: pl.DataFrame):
        dates = sample_data.get_column("contract_date")
        feats = build_features(dates)
        assert len(feats) == len(dates)

    def test_fourier_bounds(self, sample_data: pl.DataFrame):
        dates = sample_data.get_column("contract_date")
        feats = build_features(dates)
        for col in ["sin1", "cos1", "sin2", "cos2"]:
            vals = feats.get_column(col).to_numpy()
            assert np.all(vals >= -1.0 - 1e-9)
            assert np.all(vals <= 1.0 + 1e-9)

    def test_holiday_flags_binary(self, sample_data: pl.DataFrame):
        dates = sample_data.get_column("contract_date")
        feats = build_features(dates)
        for col in ["is_summer", "is_winter"]:
            vals = set(feats.get_column(col).to_list())
            assert vals <= {0, 1}


class TestTrendsMonthlyMultiplier:
    def test_mean_one(self):
        trends = pl.DataFrame(
            {
                "month": list(range(1, 13)),
                "value_mean": [80, 60, 70, 90, 100, 110, 50, 45, 120, 95, 85, 75],
            }
        )
        result = trends_monthly_multiplier(trends)
        mult = result.get_column("month_multiplier").to_numpy()
        assert abs(np.mean(mult) - 1.0) < 1e-6

    def test_all_months_present(self):
        trends = pl.DataFrame(
            {
                "month": [1, 6, 12],
                "value_mean": [100.0, 50.0, 75.0],
            }
        )
        result = trends_monthly_multiplier(trends)
        assert len(result) == 12


class TestFitAndPredict:
    def test_fit_returns_components(self, sample_data: pl.DataFrame):
        gp, scaler, x_train = fit_gp_with_calendar(sample_data)
        assert gp is not None
        assert scaler is not None
        assert "y_deseasonal" in x_train.columns

    def test_predict_daily_shape(self, sample_data: pl.DataFrame):
        gp, scaler, _ = fit_gp_with_calendar(sample_data)
        preds = predict_daily(
            gp,
            scaler,
            dt.date(2025, 7, 1),
            dt.date(2025, 12, 31),
        )
        expected_cols = {"contract_date", "pred_mean", "pred_lo", "pred_hi"}
        assert set(preds.columns) == expected_cols
        assert len(preds) == (dt.date(2025, 12, 31) - dt.date(2025, 7, 1)).days + 1

    def test_confidence_interval_ordering(self, sample_data: pl.DataFrame):
        gp, scaler, _ = fit_gp_with_calendar(sample_data)
        preds = predict_daily(
            gp,
            scaler,
            dt.date(2025, 7, 1),
            dt.date(2025, 9, 30),
        )
        lo = preds.get_column("pred_lo").to_numpy()
        mean = preds.get_column("pred_mean").to_numpy()
        hi = preds.get_column("pred_hi").to_numpy()
        assert np.all(lo <= mean)
        assert np.all(mean <= hi)


class TestFillMissing:
    def test_fill_preserves_observed(self, sample_data: pl.DataFrame):
        gp, scaler, _ = fit_gp_with_calendar(sample_data)
        preds = predict_daily(
            gp,
            scaler,
            dt.date(2024, 1, 1),
            dt.date(2024, 3, 31),
        )
        obs = sample_data.filter(pl.col("contract_date") <= dt.date(2024, 3, 31))
        filled = fill_missing_with_gp(obs, preds)
        assert "filled" in filled.columns
        assert "registration_time_filled" in filled.columns
        observed_rows = filled.filter(~pl.col("filled"))
        assert len(observed_rows) > 0
