from __future__ import annotations

import math
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Literal,
    Protocol,
)

import numpy as np
import polars as pl
from numpy.typing import NDArray
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import (
    RBF,
    ConstantKernel,
    WhiteKernel,
)
from sklearn.preprocessing import StandardScaler

if TYPE_CHECKING:
    import datetime as dt
    from collections.abc import Callable

    from polars._typing import IntoExprColumn

# -------------------------- utils --------------------------

ArrayF = NDArray[np.float64]

type ArrayAny = np.ndarray[tuple[Any, ...], np.dtype[Any]]


class ConvToArrayF(Protocol):
    def to_numpy(self) -> ArrayF: ...


def _as_array_f(x: ConvToArrayF) -> ArrayF:
    return x.to_numpy().astype(float)


def _gauss_bump(days_to_center: np.ndarray, sigma: float) -> ArrayF:
    """Smooth 'bump' feature around an anchor date (in days)."""
    return np.exp(-0.5 * (days_to_center / sigma) ** 2)


def _days_to_anchor(dates: pl.Series, month: int, day: int) -> ArrayF:
    """
    Signed days from each date to the YEAR's anchor (e.g., 1 Sep).
    dates: pl.Series[Date or Datetime]
    """
    return _as_array_f(
        pl.DataFrame({"d": dates.cast(pl.Date)})
        .with_columns(year=pl.col("d").dt.year())
        .with_columns(
            anchor=pl.datetime(
                year=pl.col("year"),
                month=pl.lit(month),
                day=pl.lit(day),
                time_unit="us",
            ).cast(pl.Date),
        )
        .with_columns(delta=(pl.col("d") - pl.col("anchor")).dt.total_days())
        .select("delta")
    ).reshape(-1)


def _erf_np(x: float | np.floating[Any]) -> np.float64:
    return np.float64(math.erf(float(x)))


def _typed_vectorize[**Ps, R: np.generic](f: Callable[Ps, R], any_array: ArrayAny) -> NDArray[R]:
    return np.vectorize(f)(*any_array)  # type: ignore[no-any-return]


# -------------------------- feature engineering --------------------------


def build_features(dates: pl.Series) -> pl.DataFrame:
    """
    Academic-year features (NL-ish):
    - yearly seasonality (Fourier sin/cos),
    - pre-semester bumps around 1 Feb and 1 Sep,
    - exam windows bumps around 31 Jan and 30 Jun,
    - holiday flags (summer Jul-Aug, winter ~Dec 20-Jan 7).
    Returns a DataFrame with 'contract_date' plus feature columns.
    """
    year_len: Final[float] = 365.25
    two_pi = 2.0 * math.pi

    d = dates.cast(pl.Date)

    df = (
        pl.DataFrame({"contract_date": d})
        .with_columns(
            doy=pl.col("contract_date").dt.ordinal_day().cast(pl.Float64),
            month=pl.col("contract_date").dt.month(),
            day=pl.col("contract_date").dt.day(),
        )
        .with_columns(
            sin1=(pl.col("doy") * (two_pi / year_len)).sin(),
            cos1=(pl.col("doy") * (two_pi / year_len)).cos(),
            sin2=(pl.col("doy") * (2.0 * two_pi / year_len)).sin(),
            cos2=(pl.col("doy") * (2.0 * two_pi / year_len)).cos(),
        )
        .hstack(
            pl.DataFrame(
                {
                    "pre_sep": _gauss_bump(_days_to_anchor(d, 9, 1), sigma=20.0),
                    "pre_feb": _gauss_bump(_days_to_anchor(d, 2, 1), sigma=15.0),
                    "exam_jan": _gauss_bump(_days_to_anchor(d, 1, 31), sigma=12.0),
                    "exam_jun": _gauss_bump(_days_to_anchor(d, 6, 30), sigma=12.0),
                }
            )
        )
        .with_columns(
            is_summer=((pl.col("month") == 7) | (pl.col("month") == 8)).cast(pl.Int8),
            is_winter=(
                ((pl.col("month") == 12) & (pl.col("day") >= 20))
                | ((pl.col("month") == 1) & (pl.col("day") <= 7))
            ).cast(pl.Int8),
        )
    )

    return df.select(
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
    )


# -------------------------- trends monthly multiplier --------------------------


def trends_monthly_multiplier(
    trends_monthly: pl.DataFrame,
    *,
    column: str = "value_mean",
    strength: float = 1.0,
    smooth_radius: int = 0,
) -> pl.DataFrame:
    """
    Convert monthly Trends means into a multiplicative profile (mean=1.0).
    Optionally smooth across neighboring months and temper with `strength`.
    Returns a DataFrame with columns: month, month_multiplier.
    """
    s = (
        trends_monthly.select(pl.col("month").cast(pl.Int32), pl.col(column).cast(pl.Float64))
        .unique(subset=["month"])
        .sort("month")
    )

    base = pl.DataFrame({"month": np.arange(1, 13, dtype=np.int32)})
    s = base.join(s, on="month", how="left")

    mu = float(s.select(pl.col(column).mean()).item())
    s = s.with_columns(pl.col(column).fill_null(mu))

    vals = _as_array_f(s.get_column(column))

    if smooth_radius > 0:
        idx_template = np.arange(-smooth_radius, smooth_radius + 1, dtype=np.int32)
        vals = np.array([float(np.mean(vals[(i + idx_template) % 12])) for i in range(12)])

    vals = vals / float(vals.mean())

    if strength != 1.0:
        vals = vals ** float(strength)

    return pl.DataFrame({"month": np.arange(1, 13, dtype=np.int32), "month_multiplier": vals})


# -------------------------- fit + predict --------------------------


def _aggregate_weekly(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate daily data to weekly means to reduce GP training size."""
    return (
        df.with_columns(
            week_start=pl.col("contract_date").dt.truncate("1w"),
        )
        .group_by("week_start")
        .agg(
            contract_date=pl.col("contract_date").min(),
            registration_time=pl.col("registration_time").mean(),
        )
        .sort("contract_date")
    )


def fit_gp_with_calendar(
    df: pl.DataFrame,
    month_mult: pl.DataFrame | None = None,
) -> tuple[GaussianProcessRegressor, StandardScaler, pl.DataFrame]:
    """
    Fit GP on (optionally) de-seasonalized y using a monthly multiplier.
    Expects df with columns: contract_date, registration_time.

    Training data is aggregated to weekly means to keep the kernel matrix
    small (n_weeks² instead of n_days²).
    """
    scaler = StandardScaler()

    df_local = df.with_columns(contract_date=pl.col("contract_date").cast(pl.Date)).sort(
        "contract_date"
    )

    df_weekly = _aggregate_weekly(df_local)

    feats = build_features(df_weekly.get_column("contract_date"))

    y = _as_array_f(df_weekly.get_column("registration_time").cast(pl.Float64))

    if month_mult is not None:
        mm_joined = (
            feats.with_columns(month=pl.col("contract_date").dt.month())
            .join(month_mult, on="month", how="left")
            .with_columns(month_multiplier=pl.col("month_multiplier").fill_null(1.0))
        )
        mm: ArrayF = _as_array_f(mm_joined.get_column("month_multiplier"))
        mm[~np.isfinite(mm)] = 1.0
        y = y / mm

    x = scaler.fit_transform(_as_array_f(feats.drop("contract_date")))

    k = ConstantKernel(1.0, (1e-3, 1e3)) * RBF(
        length_scale=1.0, length_scale_bounds=(1e-1, 1e2)
    ) + WhiteKernel(noise_level=0.1, noise_level_bounds=(1e-6, 1e1))

    gp = GaussianProcessRegressor(
        kernel=k,
        alpha=1e-6,
        normalize_y=True,
        n_restarts_optimizer=5,
        random_state=42,
    )

    gp.fit(x, y)

    x_train = feats.with_columns(y_deseasonal=pl.Series(y))

    return gp, scaler, x_train


def predict_daily(
    gp: GaussianProcessRegressor,
    scaler: StandardScaler,
    start: dt.datetime | dt.date | IntoExprColumn,
    end: dt.datetime | dt.date | IntoExprColumn,
    month_mult: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """
    Predict daily; if a multiplier is provided, reapply multiplicatively
    to the mean and std (assume variance scales similarly).
    """
    dates = pl.date_range(start, end, interval="1d", eager=True)
    feats = build_features(pl.Series(dates))
    x_raw = _as_array_f(feats.drop("contract_date"))
    x = scaler.transform(x_raw)

    def prediction(mean: ArrayAny, std: ArrayAny, dates: pl.Series) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "contract_date": dates,
                "pred_mean": mean,
                "pred_lo": np.maximum(mean - 1.96 * std, 0.0),
                "pred_hi": mean + 1.96 * std,
            }
        )

    match gp.predict(x, return_std=True):
        case (mean_ds, std_ds):
            if month_mult is None:
                return prediction(mean_ds, std_ds, dates)

            mm: ArrayF = _as_array_f(
                pl.DataFrame({"contract_date": dates})
                .with_columns(month=pl.col("contract_date").dt.month())
                .join(month_mult, on="month", how="left")
                .with_columns(month_multiplier=pl.col("month_multiplier").fill_null(1.0))
                .get_column("month_multiplier")
            )
            mm[~np.isfinite(mm)] = 1.0

            return prediction(mean_ds * mm, std_ds * mm, dates)
        case _:
            raise ValueError("GP prediction failed; check input data.")


def fill_missing_with_gp(
    df_obs: pl.DataFrame,
    df_pred: pl.DataFrame,
) -> pl.DataFrame:
    """
    Left-join df_pred onto all daily dates, keep observed values when available,
    otherwise use GP mean. Adds a column 'filled' (bool).
    """
    obs = df_obs.with_columns(contract_date=pl.col("contract_date").cast(pl.Date))
    pred = df_pred.with_columns(contract_date=pl.col("contract_date").cast(pl.Date))

    return pred.join(
        obs.select("contract_date", "registration_time"), on="contract_date", how="left"
    ).with_columns(
        registration_time_filled=pl.when(pl.col("registration_time").is_not_null())
        .then(pl.col("registration_time"))
        .otherwise(pl.col("pred_mean")),
        filled=pl.col("registration_time").is_null(),
    )


def add_prob_good_enough(
    df_pred: pl.DataFrame,
    my_time_fn: Callable[[object], float],
    *,
    direction: Literal["at_least", "at_most"] = "at_least",
) -> pl.DataFrame:
    """
    Add:
      - my_time: your value at each date
      - prob_good_enough: probability (%) under Normal predictive dist
      - ci_pct: relative position of my_time within [pred_lo, pred_hi] (0..100)

    direction="at_least" -> P(Y <= my_time)  (lower required time is better)
    direction="at_most"  -> P(Y >= my_time)  (if 'higher is better')
    """
    with_my = df_pred.with_columns(my_time=pl.col("contract_date").map_elements(my_time_fn))

    def _get_column(col_name: str) -> ArrayF:
        return _as_array_f(with_my.get_column(col_name))

    lo = _get_column("pred_lo")
    hi = _get_column("pred_hi")

    mu = _get_column("pred_mean")
    m = _get_column("my_time")

    sigma = np.maximum((hi - lo) / (2.0 * 1.96), 1e-9)

    z = (m - mu) / sigma

    cdf = 0.5 * (1.0 + _typed_vectorize(_erf_np, z / math.sqrt(2.0)))
    prob = cdf if direction == "at_least" else (1.0 - cdf)

    denom = hi - lo
    with np.errstate(divide="ignore", invalid="ignore"):
        ci_pos = np.clip((m - lo) / denom, 0.0, 1.0)

    return with_my.hstack(
        pl.DataFrame(
            {
                "prob_good_enough": prob * 100.0,
                "ci_pct": ci_pos * 100.0,
            }
        )
    )
