"""Stage D: solar geometry, and the interval-labelling test that gates radiometry.

Two products:

  * a 30-minute solar table (SZA, azimuth, clear-sky irradiance, extraterrestrial
    PAR) for the tower, 2008 onward, on ``Etc/GMT+5``;
  * the resolution of whether an archived timestamp marks the **start**, the
    **centre**, or the **end** of its averaging interval.

The second one matters more than it looks. fAPAR is a ratio of two PAR streams
recorded by different loggers; if their stamp conventions differ, every fAPAR
value carries a systematic bias, worst where irradiance changes fastest --
morning and evening, which is exactly where the paper's filters operate. So it
is resolved here, before any fAPAR code is written.

The test: on clear days, locate the peak of the observed PAR curve and compare
it to pvlib's solar transit. If a stamp ``t`` represents the average over
``[t, t+dt]``, using ``t`` as the coordinate pulls the apparent peak earlier by
``dt/2``; if it represents ``[t-dt, t]``, it pushes it later by the same amount.
So the measured lag reads off the convention directly.

Locating the peak by **parabola vertex** over the five points around the maximum,
not by intensity-weighted centroid. The centroid integrates the whole daily
curve and is therefore biased by afternoon convective cloud, which is asymmetric
at this site: it returned -0.34 h and drifted toward zero as the clear-day
filter tightened, which is the signature of a contaminated estimator rather than
a stamp offset. The vertex uses only the peak neighbourhood and is immune.

**Result (hf004-01, 2012-2023, 281 clear Mar-Oct days): median lag -0.5048 h,
95% CI [-0.5147, -0.4897].** That is ``interval_start`` for a 1-hour step, and
it excludes centre-labelling and end-labelling by a wide margin. A stamp at
``t`` in hf004 is the average over ``[t, t+1h]``. The month-by-month medians run
-0.47 to -0.53 across March-October, i.e. the offset is constant, as a stamp
convention must be and as cloud asymmetry would not be.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pvlib

from wp0 import io

# Photon flux per joule of broadband shortwave: PAR is ~45% of shortwave by
# energy, and ~4.57 umol per joule within the PAR waveband.
PAR_FRACTION = 0.45
UMOL_PER_J = 4.57
PAR_PER_GHI = PAR_FRACTION * UMOL_PER_J        # umol m-2 s-1 per W m-2
SOLAR_CONSTANT = 1361.0                        # W m-2

LOCATION = pvlib.location.Location(
    io.TOWER_LAT, io.TOWER_LON, tz=io.TZ, altitude=io.TOWER_ELEV_M, name="HF EMS")

DEFAULT_START = "2008-01-01"
CLEAR_KT_MIN = 0.65        # daily clearness needed to call a day clear
CLEAR_CV_MAX = 0.12        # max CV of observed/clear-sky within the high-sun window
HIGH_SUN_FRAC = 0.5        # "high sun" = clear-sky PAR >= this x the day's max
LABEL_TEST_MONTHS = (3, 10)  # Mar-Oct; the winter peak is too flat to fit hourly


def grid(start: str = DEFAULT_START, end: str | None = None,
         freq: str = "30min") -> pd.DataFrame:
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    idx = pd.date_range(start, end, freq=freq, tz=io.TZ)
    pos = LOCATION.get_solarposition(idx)
    cs = LOCATION.get_clearsky(idx, model="ineichen")

    out = pd.DataFrame(index=idx)
    out["sza_deg"] = pos["apparent_zenith"].to_numpy()
    out["sza_true_deg"] = pos["zenith"].to_numpy()
    out["azimuth_deg"] = pos["azimuth"].to_numpy()
    out["elevation_deg"] = pos["apparent_elevation"].to_numpy()
    out["clearsky_ghi"] = cs["ghi"].to_numpy()
    out["clearsky_dni"] = cs["dni"].to_numpy()
    out["clearsky_dhi"] = cs["dhi"].to_numpy()
    out["clearsky_par"] = out["clearsky_ghi"] * PAR_PER_GHI

    cosz = np.cos(np.radians(out["sza_true_deg"]))
    doy = out.index.dayofyear.to_numpy()
    e0 = 1 + 0.033 * np.cos(2 * np.pi * doy / 365.0)     # earth-sun distance
    out["toa_ghi"] = np.maximum(SOLAR_CONSTANT * e0 * cosz, 0.0)
    out["toa_par"] = out["toa_ghi"] * PAR_PER_GHI
    out["daytime"] = out["elevation_deg"] > 0
    out.index.name = "datetime_est"
    return out.reset_index()


# --------------------------------------------------------------------------
# interval labelling
# --------------------------------------------------------------------------

def _load_par29() -> pd.Series:
    df = io.read_raw("hf004_final", usecols=["datetime", "par.29"])
    t = pd.to_datetime(df["datetime"]).dt.tz_localize(io.TZ)
    s = pd.Series(df["par.29"].to_numpy(float), index=t, name="par29")
    # Small negatives are sensor zero-offset: clamp, do not discard.
    return s.clip(lower=0.0).dropna()


def interval_labelling_test(start: str = "2012-01-01",
                            end: str = "2023-12-31") -> pd.DataFrame:
    """Per clear day: PAR peak time minus pvlib solar transit, in hours.

    Reports both estimators. ``lag_vertex_h`` is the one to trust;
    ``lag_centroid_h`` is retained so the cloud-asymmetry bias stays visible.
    """
    par = _load_par29().loc[start:end]
    if par.empty:
        return pd.DataFrame()

    step_h = float(pd.Series(par.index).diff().dt.total_seconds().median() / 3600.0)
    g = grid(start, end, freq=f"{int(round(step_h * 60))}min").set_index("datetime_est")

    frame = pd.DataFrame({"par": par, "cs": g["clearsky_par"].reindex(par.index)}).dropna()
    frame = frame[frame["cs"] > 50]                 # daylight only
    frame["day"] = frame.index.normalize()
    frame["hour"] = frame.index.hour + frame.index.minute / 60.0

    days = pd.DatetimeIndex(sorted(frame["day"].unique()))
    tr = LOCATION.get_sun_rise_set_transit(days, method="spa")["transit"]
    noon = pd.Series((tr.dt.hour + tr.dt.minute / 60.0
                      + tr.dt.second / 3600.0).to_numpy(), index=days)

    m0, m1 = LABEL_TEST_MONTHS
    rows = []
    for day, d in frame.groupby("day"):
        n0 = noon.get(day)
        if n0 is None or pd.isna(n0) or len(d) < 8 or not (m0 <= day.month <= m1):
            continue
        hi = d[d["cs"] >= HIGH_SUN_FRAC * d["cs"].max()]
        if len(hi) < 4:
            continue
        r = hi["par"] / hi["cs"]
        cv = float(r.std() / r.mean()) if r.mean() > 0 else np.inf
        kt = float(d["par"].sum() / d["cs"].sum())
        if kt < CLEAR_KT_MIN or cv > CLEAR_CV_MAX:
            continue

        w = d[np.abs(d["hour"] - n0) <= 4.0]        # symmetric about solar noon
        centroid = (float((w["hour"].to_numpy() * w["par"].to_numpy()).sum()
                          / w["par"].sum()) if len(w) >= 7 and w["par"].sum() > 0
                    else np.nan)

        dd = d.sort_values("hour").reset_index(drop=True)
        k = int(dd["par"].idxmax())
        seg = dd.iloc[max(0, k - 2):min(len(dd), k + 3)]
        vertex = np.nan
        if len(seg) >= 5:
            c = np.polyfit(seg["hour"].to_numpy(), seg["par"].to_numpy(), 2)
            if c[0] < 0:
                vertex = -c[1] / (2 * c[0])

        rows.append({"day": day, "kt": kt, "cv": cv, "solar_noon_h": n0,
                     "lag_centroid_h": centroid - n0 if centroid == centroid else np.nan,
                     "lag_vertex_h": vertex - n0 if vertex == vertex else np.nan,
                     "n_obs": len(d)})

    res = pd.DataFrame(rows)
    if not res.empty:
        res["step_h"] = step_h
    return res


def interpret_lag(res: pd.DataFrame, step_h: float,
                  n_boot: int = 4000, seed: int = 0) -> tuple[str, float, str]:
    """Map the median vertex lag onto a stamp convention, with a bootstrap CI."""
    if res.empty or res["lag_vertex_h"].notna().sum() < 20:
        return "unknown", float("nan"), "too few clear days passed the filter"
    v = res["lag_vertex_h"].dropna().to_numpy()
    lag = float(np.median(v))
    rng = np.random.default_rng(seed)
    bs = np.median(rng.choice(v, (n_boot, len(v))), axis=1)
    lo, hi = float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))

    half = step_h / 2.0
    candidates = {"interval_start": -half, "centre_or_instantaneous": 0.0,
                  "interval_end": +half}
    verdict = min(candidates, key=lambda k: abs(lag - candidates[k]))
    detail = (f"vertex lag {lag:+.4f} h, 95% CI [{lo:+.4f}, {hi:+.4f}], "
              f"n={len(v)} clear days; expected {candidates[verdict]:+.3f} h for "
              f"'{verdict}' at a {step_h:.2f} h step "
              f"(centroid estimator gives {res['lag_centroid_h'].median():+.3f} h "
              f"and is biased toward zero by afternoon cloud)")
    return verdict, lag, detail


def run(start: str = DEFAULT_START) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    g = grid(start)
    res = interval_labelling_test(start)
    step_h = float(res["step_h"].iloc[0]) if not res.empty else float("nan")
    verdict, lag, detail = interpret_lag(res, step_h)

    io.write(g, "solar_30min.csv")
    io.write(res, "interval_labelling_clear_days.csv")
    io.record(
        stage="D",
        inputs=["hf004_final"],
        params={"tz": io.TZ, "location": [io.TOWER_LAT, io.TOWER_LON, io.TOWER_ELEV_M],
                "clearsky_model": "ineichen", "par_per_ghi": PAR_PER_GHI,
                "clear_kt_min": CLEAR_KT_MIN, "clear_cv_max": CLEAR_CV_MAX,
                "label_test_months": list(LABEL_TEST_MONTHS),
                "label_estimator": "parabola vertex over the 5 points at the peak"},
        outputs=["solar_30min.csv", "interval_labelling_clear_days.csv"],
        notes=f"hf004 stamp convention: {verdict}. {detail}",
    )
    return g, res, {"verdict": verdict, "median_lag_h": lag, "detail": detail,
                    "n_clear_days": len(res), "step_h": step_h}
