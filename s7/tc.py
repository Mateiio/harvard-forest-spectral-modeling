"""Triple collocation, applied not invented.

Standard covariance-form TC (Stoffelen 1998; McColl et al. 2014 for the skill
term). For three systems each linearly related to a common latent T,

    X_i = a_i + b_i T + e_i ,      Q_ij = Cov(X_i, X_j)

the error variance of each, **in its own units**, is

    var(e_x) = Q_xx - Q_xy Q_xz / Q_yz          (and cyclic)

and Extended TC adds the correlation of each system with the unknown truth,

    rho^2(x,T) = Q_xy Q_xz / (Q_xx Q_yz) .

Three things this module refuses to take on faith.

**Linearity.** TC's model is linear. NDVI saturates against LAI, and a
saturating relationship does not merely add noise -- it breaks the estimator.
:func:`linearity` tests it before any error variance is reported.

**Independence of errors.** HLS and MODIS share optical physics, similar bands
and comparable atmospheric correction, so their errors are correlated by
construction and the assumption is known to fail here. Rather than claim a new
method for that -- Correlated Triple Collocation and Extended Quadruple
Collocation already exist -- :func:`sensitivity` sweeps the unknown error
covariance and reports which way the estimates move and how far.

**Independence of samples.** Five MODIS cells serve 33 plots, so on any date
the MODIS value repeats across every plot in a cell. Rows are not independent
and the naive n of ~1800 is a fiction; the bootstrap blocks on (date, cell).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

NAMES = ("ground", "hls", "modis")


def _cov(a, b) -> float:
    return float(np.cov(a, b, ddof=1)[0, 1])


def classical(x, y, z, err_cov_yz: float = 0.0) -> dict:
    """TC error variances and ETC skill.

    ``err_cov_yz`` is an assumed covariance between the errors of the two
    satellite systems. Zero recovers classical TC; a positive value is the
    physically expected case here and is what :func:`sensitivity` sweeps.
    """
    x, y, z = map(np.asarray, (x, y, z))
    Qxx, Qyy, Qzz = np.var(x, ddof=1), np.var(y, ddof=1), np.var(z, ddof=1)
    Qxy, Qxz, Qyz = _cov(x, y), _cov(x, z), _cov(y, z)
    Qyz_c = Qyz - err_cov_yz
    if min(abs(Qxy), abs(Qxz), abs(Qyz_c)) < 1e-12:
        return {}

    var_ex = Qxx - Qxy * Qxz / Qyz_c
    var_ey = Qyy - Qxy * Qyz_c / Qxz
    var_ez = Qzz - Qxz * Qyz_c / Qxy

    out = {}
    for nm, v, Q in zip(NAMES, (var_ex, var_ey, var_ez), (Qxx, Qyy, Qzz)):
        out[f"var_err_{nm}"] = float(v)
        out[f"sd_err_{nm}"] = float(np.sqrt(v)) if v > 0 else float("nan")
        # ETC: squared correlation with the unknown truth
        rho2 = 1.0 - v / Q
        out[f"rho2_truth_{nm}"] = float(rho2)
        out[f"snr_{nm}"] = float(rho2 / (1 - rho2)) if 0 < rho2 < 1 else float("nan")
        out[f"frac_var_error_{nm}"] = float(v / Q)
    out["err_cov_yz"] = float(err_cov_yz)
    out["negative_variance"] = bool(min(var_ex, var_ey, var_ez) < 0)
    return out


def linearity(t: pd.DataFrame, cols=("pai", "hls", "modis_lai")) -> pd.DataFrame:
    """Is each pair linearly related, as TC's model requires?

    Reports Pearson against Spearman (a gap means monotone but curved) and an
    F-test for a quadratic term. A significant quadratic is a warning that the
    TC estimates below are model error, not measurement error.
    """
    rows = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = t[cols[i]].to_numpy(), t[cols[j]].to_numpy()
            m = np.isfinite(a) & np.isfinite(b)
            a, b = a[m], b[m]
            pear = stats.pearsonr(a, b)[0]
            spear = stats.spearmanr(a, b)[0]
            X1 = np.column_stack([np.ones_like(a), a])
            X2 = np.column_stack([X1, a ** 2])
            r1 = b - X1 @ np.linalg.lstsq(X1, b, rcond=None)[0]
            r2 = b - X2 @ np.linalg.lstsq(X2, b, rcond=None)[0]
            ss1, ss2 = float(r1 @ r1), float(r2 @ r2)
            df2 = len(a) - 3
            F = (ss1 - ss2) / (ss2 / df2) if ss2 > 0 else np.inf
            p = float(1 - stats.f.cdf(F, 1, df2))
            rows.append({"pair": f"{cols[i]} ~ {cols[j]}", "n": len(a),
                         "pearson": pear, "spearman": spear,
                         "spearman_minus_pearson": spear - pear,
                         "quadratic_F": float(F), "quadratic_p": p,
                         "curvature_reduces_ss_pct": 100 * (ss1 - ss2) / ss1})
    return pd.DataFrame(rows)


def block_bootstrap(t: pd.DataFrame, cols=("pai", "hls", "modis_lai"),
                    block=("ground_date", "appeears_pixel"),
                    n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Resample whole (date, MODIS cell) blocks, not rows.

    Plots inside one MODIS cell share the same MODIS value on a given date, so
    row resampling would treat ~1800 correlated rows as independent and give
    confidence intervals several times too narrow.
    """
    rng = np.random.default_rng(seed)
    keys = list(t.groupby(list(block)).groups.values())
    out = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        idx = np.concatenate([keys[k].to_numpy() for k in pick])
        s = t.loc[idx]
        r = classical(s[cols[0]], s[cols[1]], s[cols[2]])
        if r and not r["negative_variance"]:
            out.append(r)
    return pd.DataFrame(out)


def sensitivity(t: pd.DataFrame, cols=("pai", "hls", "modis_lai"),
                fracs=(0.0, 0.05, 0.10, 0.20, 0.30, 0.40)) -> pd.DataFrame:
    """How the estimates move as the two satellites' errors are allowed to correlate.

    ``frac`` is the assumed error covariance as a fraction of the observed
    HLS-MODIS covariance. The direction is the point: shared satellite error is
    read by classical TC as shared *signal*, which flatters both satellites and
    penalises the ground.
    """
    rows = []
    Qyz = _cov(t[cols[1]], t[cols[2]])
    for f in fracs:
        r = classical(t[cols[0]], t[cols[1]], t[cols[2]], err_cov_yz=f * Qyz)
        if not r:
            continue
        r["assumed_err_corr_frac"] = f
        rows.append(r)
    return pd.DataFrame(rows)


def effective_n(t: pd.DataFrame,
                block=("ground_date", "appeears_pixel")) -> dict:
    return {"n_rows": int(len(t)),
            "n_blocks": int(t.groupby(list(block)).ngroups),
            "n_ground_dates": int(t["ground_date"].nunique()),
            "n_modis_cells": int(t["appeears_pixel"].nunique()),
            "note": "rows within a (date, MODIS cell) block share one MODIS "
                    "value; n_blocks is the honest sample size for anything "
                    "MODIS-driven"}
