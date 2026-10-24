"""Study 2 - ANGULAR. Shared constants, QC, solar geometry and canopy equations.

Imported by Study2_01..05 notebooks. Hand-written module, not an nbconvert export.

Equations are transcribed from docs/ssrn-4237352.pdf (extracted 2026-08-05) and
numbered as in that paper. Where the printed form is wrong, both forms are
implemented and the choice is made empirically at Gate G3 -- see EQ8_FORM.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Site and model constants
# ---------------------------------------------------------------------------

# EMS tower, from HF375-01. HF102 gives +42.537755, -72.171478, 340 m; the two
# agree to ~1 m, which is far below anything that matters for solar position.
EMS_LAT, EMS_LON, EMS_ALT = 42.537764, -72.171479, 340.0

# Harvard Forest archives are Eastern Standard Time year-round, no DST.
# Confirmed by the hf004 column literally named "hour.hour.est.utc.5.".
# Etc/GMT+5 is UTC-5 (POSIX sign convention is inverted -- this is EST).
SITE_TZ = "Etc/GMT+5"

# Deep-canopy fAPAR. The paper states 0.94 (section 2.3.4, after eq 9).
# NOTE: Trash/killtest.py uses 0.95 for Study 1. That is a real inconsistency
# and Study 1's numbers should be re-run against 0.94.
PINF = 0.94

# Ratio of average projected leaf area on horizontal vs vertical surfaces.
# The paper sets x = 3 (planophile), consistent with chi_l in its two-stream
# runs. x = 1 is the spherical LAD. This choice dominates the modelled SZA
# response -- see selftest() -- so it is never silently defaulted in analysis.
X_LAD_PAPER = 3.0
X_LAD_SPHERICAL = 1.0

# Paper's filters (section 2.2). PAR_MIN excludes low light; the solar-time
# window is a de-facto SZA filter that truncates precisely the high-SZA tail
# H2.1 targets, so it is a toggle in this study, never a default.
PAR_MIN = 200.0                     # umol m-2 s-1, above-canopy
SOLAR_TIME_WINDOW = (7.0, 17.0)     # hours, local solar time

# Campbell datalogger sentinel, left unconverted in places. Scan for it in
# every numeric column -- the two documented cases are examples, not a list.
SENTINEL = 7999.0

# Below-canopy PAR sensors in hf206-05, with logger attribution taken from the
# HF206 methods text. The `_ave` column DESCRIPTIONS wrongly assign all six to
# EMS1; the methods and the `_max` descriptions put E3/F3/F2 on EMS2. Trust the
# methods. Pixel and MODIS cell membership from docs/00-research-program.md s7.
SENSORS = pd.DataFrame(
    [
        # plot, logger,  column,        wholly_inside_hls_pixel, modis_cell
        ("C2", "EMS1", "par_c2", False, "pixel_4"),
        ("E3", "EMS2", "par_e3", True,  "pixel_1"),
        ("B2", "EMS1", "par_b2", False, "pixel_4"),
        ("F3", "EMS2", "par_f3", False, "pixel_1"),
        ("F2", "EMS2", "par_f2", False, "pixel_1"),
        ("C3", "EMS1", "par_c3", False, "pixel_4"),
    ],
    columns=["plot", "logger", "col", "wholly_inside", "modis_cell"],
)

# Lowest-missingness plots, used as primary. E3 is the only one wholly inside
# its HLS pixel, so it is the clean single-plot case.
PRIMARY_PLOTS = ["B2", "C2", "E3"]

DATA = r"c:\crtusers\matei\prj\data"

PATHS = {
    # Below-canopy PAR, 30-min, 2008-05-02 -> 2025-01-09. MD5 verified against
    # the catalog: 94d70d32eaaee53996b25fd5dafe6715.
    "hf206_05": rf"{DATA}\HF206\hf206-05-EMS-understory.csv",
    "hf206_02": rf"{DATA}\HF206\hf206-02-HK-micro-2014-present.csv",
    # EMS tower. hf004-01 carries par.29 (above canopy), par.ref (reflected,
    # = PAR_cr in eq 3) and measured par.dir / par.dfs. Everything eq 3 needs,
    # at the same tower as the understory sensors.
    "hf004_01": rf"{DATA}\HF004\hf004-01-final.csv",
    "hf004_02": rf"{DATA}\HF004\hf004-02-filled.csv",
    # HDW walk-up tower, ~400 m SW. parac_up/parac_down above canopy at 28 m;
    # hf282-02 adds two more understory sensors (parus1/parus2) from 2015.
    "hf282_01": rf"{DATA}\HF282\hf282-01-hdwd-tower.csv",
    "hf282_02": rf"{DATA}\HF282\hf282-02-hdwd-tower-understory.csv",
    # Barn tower. Has measured `diffuse` and `direct` from 2011-11-23.
    "hf249_01": rf"{DATA}\HF249\hf249-01-radiometric.csv",
    "hf069_01": rf"{DATA}\HF069\hf069-01-lai-plot.csv",
    "hf375_02": rf"{DATA}\HF375\hf375-02-field-sites-plots.csv",
    "hf365_ndvi": rf"{DATA}\HF365Dataset\hf365-02-hls-ndvi.csv",
    "hf365_nirv": rf"{DATA}\HF365Dataset\hf365-03-hls-nirv.csv",
    "hf365_evi2": rf"{DATA}\HF365Dataset\hf365-01-hls-evi2.csv",
}

# Above-canopy PAR columns, by source. Resolved by inspection of the headers.
ABOVE_CANOPY = {
    "hf004": {
        "path": PATHS["hf004_01"], "time": "datetime",
        "par_i": "par.29",            # incident, 29 m
        "par_ref": "par.ref.ue.m2.s",  # PAR_cr, eq 3
        "par_dir": "par.dir.ue.m2.s",
        "par_dfs": "par.dfs.ue.m2.s",
    },
    "hf004_filled": {
        "path": PATHS["hf004_02"], "time": "datetime",
        "par_i": "par.28m.filled.e.6mol.m2.s",
        "par_raw": "par.28m.e.6mol.m2.s",
        "par_dir": "pardir_ue.m2.s",
        "par_dfs": "pardfs_ue.m2.s",
    },
    "hf282": {
        "path": PATHS["hf282_01"], "time": "datetime",
        "par_i": "parac_up", "par_ref": "parac_down",
    },
}


# ---------------------------------------------------------------------------
# Canopy radiative transfer
# ---------------------------------------------------------------------------

def _campbell_denom(x: float) -> float:
    """Campbell (1990) ellipsoidal LAD normalisation, denominator of eq 12."""
    return x + 1.774 * (x + 1.182) ** -0.733


def G_theta(sza_deg, x: float = X_LAD_PAPER):
    """Leaf projection coefficient G(theta), eq 12.

        G(t) = sqrt(x^2 cos^2 t + sin^2 t) / (x + 1.774 (x + 1.182)^-0.733)

    x is the ratio of average projected leaf area on horizontal vs vertical
    surfaces: 1.0 spherical, 3.0 planophile (the paper's choice).
    """
    t = np.radians(np.asarray(sza_deg, dtype=float))
    return np.sqrt(x**2 * np.cos(t) ** 2 + np.sin(t) ** 2) / _campbell_denom(x)


def K_theta(sza_deg, x: float = X_LAD_PAPER):
    """Extinction coefficient K = G(theta)/cos(theta), the path-length term.

    Identically equal to sqrt(x^2 + tan^2 t) / (x + 1.774 (x+1.182)^-0.733),
    which is Campbell's ellipsoidal K. selftest() checks both forms agree.
    """
    t = np.radians(np.asarray(sza_deg, dtype=float))
    return G_theta(sza_deg, x) / np.cos(t)


def ft04_transmittance(lai, sza_deg, x: float = X_LAD_PAPER):
    """FT04 canopy PAR transmittance, eq 11:  exp(-G(t) L / cos t)."""
    return np.exp(-K_theta(sza_deg, x) * np.asarray(lai, dtype=float))


# Eq 8 and eq 13 both print as `P_inf - exp(...)`, which returns -0.06 at L=0.
# Because BOTH print that way it is a consistent rendering, not a one-off slip,
# so it cannot be dismissed without testing. The multiplicative form is the
# physically sensible one (0 at L=0, -> P_inf as L -> inf). Gate G3 decides.
EQ8_FORM = "multiplicative"   # "multiplicative" | "printed"


def ft04_fapar(lai, sza_deg, pinf: float = PINF, x: float = X_LAD_PAPER,
               form: str | None = None):
    """FT04 canopy fAPAR from LAI and solar zenith angle (eqs 11-13)."""
    tr = ft04_transmittance(lai, sza_deg, x)
    form = form or EQ8_FORM
    if form == "multiplicative":
        return pinf * (1.0 - tr)
    if form == "printed":
        return pinf - tr
    raise ValueError(f"unknown form {form!r}")


def beer_fapar(index, pinf: float = PINF, k: float = 0.5, form: str | None = None):
    """Beer's-law fAPAR with a fixed extinction coefficient (eqs 8/9 shape).

    Used for the stem/leaf partition, where the argument is S or L and k is the
    canopy extinction coefficient "derived from observations".
    """
    form = form or EQ8_FORM
    tr = np.exp(-k * np.asarray(index, dtype=float))
    return pinf * (1.0 - tr) if form == "multiplicative" else pinf - tr


def fapar_stem(sai, fapar_canopy, pinf: float = PINF, k: float = 0.5,
               form: str | None = None):
    """fAPAR intercepted by branches and stems, eq 9:

        fAPAR_S = (P_inf - exp(-K S)) * (1 - fAPAR_C)

    S is the stem area index -- the plant area index when LAI = 0. HF069
    measures PAI, not LAI, so S must be derived from leaf-off PAI per plot and
    L = PAI - S. This is not bookkeeping: S is the whole difference between
    fAPAR_T and fAPAR_C.
    """
    return beer_fapar(sai, pinf, k, form) * (1.0 - np.asarray(fapar_canopy, float))


def fapar_total(par_i, par_transmitted, par_reflected=0.0):
    """In-situ total fAPAR from eq 3:  Phi = PAR_i - PAR_cr - PAR_t.

    PAR reflected by the forest floor is assumed negligible, following the
    paper. par_reflected is PAR_cr, the upwelling PAR reflected by the canopy
    (hf004 `par.ref.ue.m2.s`); pass 0.0 only if deliberately omitting it.
    """
    par_i = np.asarray(par_i, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        phi = par_i - np.asarray(par_reflected, float) - np.asarray(par_transmitted, float)
        return np.where(par_i > 0, phi / par_i, np.nan)


# ---------------------------------------------------------------------------
# QC
# ---------------------------------------------------------------------------

def qc_sentinels(df: pd.DataFrame, tol: float = 0.5) -> tuple[pd.DataFrame, pd.Series]:
    """Blank +/-7999 Campbell sentinels across EVERY numeric column.

    The research program names par_f2_max and swc3_max, but those are the two
    that were noticed, not the two that exist. Scanning is the point.
    """
    out = df.copy()
    hits = {}
    for c in out.select_dtypes("number").columns:
        m = (out[c].abs() - SENTINEL).abs() < tol
        n = int(m.sum())
        if n:
            out.loc[m, c] = np.nan
            hits[c] = n
    return out, pd.Series(hits, dtype="int64").sort_values(ascending=False)


def clamp_par_floor(df: pd.DataFrame, cols, floor: float = -10.0
                    ) -> tuple[pd.DataFrame, pd.Series]:
    """Clamp small negative PAR to 0; blank implausibly large negatives.

    Small negatives (~ -3) are sensor zero-offset at night and are NORMAL:
    clamp them, do not discard. Discarding instead of clamping silently deletes
    the low-light observations, which is exactly the high-SZA tail this study
    depends on. Large negatives (par_c3_min reaches -1648) are real faults.
    """
    out = df.copy()
    report = {}
    for c in cols:
        if c not in out.columns:
            continue
        bad = out[c] < floor
        small = (out[c] < 0) & ~bad
        out.loc[bad, c] = np.nan
        out.loc[small, c] = 0.0
        report[c] = (int(bad.sum()), int(small.sum()))
    return out, pd.Series(report, dtype="object")


PHYSICAL_LIMITS = {
    # column-name substring -> (min, max). Applied by substring so that the
    # _ave/_max/_min triplets are all covered without enumerating 83 columns.
    "tsoil": (-30.0, 45.0),
    "tair": (-40.0, 45.0),
    "swc": (0.0, 1.0),
    "rh": (0.0, 100.0),
}


def qc_physical(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Blank values outside physical range (tsoil2_e 101.8 C, swc4_max 1.578)."""
    out = df.copy()
    hits = {}
    for key, (lo, hi) in PHYSICAL_LIMITS.items():
        for c in out.select_dtypes("number").columns:
            if key not in c.lower():
                continue
            m = (out[c] < lo) | (out[c] > hi)
            n = int(m.sum())
            if n:
                out.loc[m, c] = np.nan
                hits[c] = n
    return out, pd.Series(hits, dtype="int64").sort_values(ascending=False)


def load_hf206_ems(path: str | None = None, apply_qc: bool = True) -> pd.DataFrame:
    """Load hf206-05 below-canopy PAR, tz-localise, and apply the mandatory QC."""
    df = pd.read_csv(path or PATHS["hf206_05"])
    for c in df.select_dtypes("object").columns:      # HF archives carry
        df[c] = df[c].str.strip()                      # trailing spaces
    df["datetime"] = (pd.to_datetime(df["datetime"])
                        .dt.tz_localize(SITE_TZ, nonexistent="shift_forward",
                                        ambiguous="NaT"))
    if apply_qc:
        df, _ = qc_sentinels(df)
        df, _ = qc_physical(df)
        par_cols = [f"{c}_{s}" for c in SENSORS["col"] for s in ("ave", "max", "min")]
        df, _ = clamp_par_floor(df, par_cols)
    return df.sort_values("datetime").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Solar geometry
# ---------------------------------------------------------------------------

def solar_position(index: pd.DatetimeIndex) -> pd.DataFrame:
    """NREL SPA solar position at the EMS tower. Index must be tz-aware."""
    import pvlib
    if index.tz is None:
        raise ValueError("index must be tz-aware; localise to SITE_TZ first")
    sp = pvlib.solarposition.get_solarposition(index, EMS_LAT, EMS_LON,
                                               altitude=EMS_ALT)
    return sp[["apparent_zenith", "zenith", "azimuth", "apparent_elevation"]]


def solar_time_hours(index: pd.DatetimeIndex) -> pd.Series:
    """Local apparent solar time in hours, for the paper's 07:00-17:00 filter."""
    import pvlib
    eot = pvlib.solarposition.equation_of_time_spencer71(index.dayofyear)
    clock = index.hour + index.minute / 60.0
    # Etc/GMT+5 => standard meridian 75 W.
    return (clock + (EMS_LON - (-75.0)) * 4.0 / 60.0 + eot / 60.0) % 24.0


def diffuse_fraction_measured(direct, diffuse):
    """Diffuse fraction from MEASURED direct and diffuse PAR.

    hf004 (par.dir/par.dfs, 2012-) and hf249 (direct/diffuse, 2011-) both carry
    these, so for most of the study period the diffuse fraction is observed
    rather than derived from a clearness index. Prefer this everywhere it
    exists and flag derived values explicitly where it does not.
    """
    direct = np.asarray(direct, dtype=float)
    diffuse = np.asarray(diffuse, dtype=float)
    total = direct + diffuse
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(total > 0, diffuse / total, np.nan)


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------

def block_cv_splits(df: pd.DataFrame, by: str = "year"):
    """Leave-one-block-out splits, blocking by year or by day.

    Consecutive half-hours are near-identical, so a random split leaks
    catastrophically and manufactures an R^2 near 1. Always report a blocked
    score; report the random score alongside it to make the leak visible.
    """
    if by == "year":
        key = df["datetime"].dt.year
    elif by == "day":
        key = df["datetime"].dt.floor("D")
    else:
        raise ValueError("by must be 'year' or 'day'")
    for block in key.drop_duplicates().sort_values():
        m = (key == block).to_numpy()
        yield block, np.where(~m)[0], np.where(m)[0]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def selftest(verbose: bool = True) -> pd.DataFrame:
    """Verify the canopy equations against identities and published values."""
    rows = []

    def check(name, got, want, tol=1e-6):
        ok = bool(np.all(np.abs(np.asarray(got) - np.asarray(want)) < tol))
        rows.append({"check": name, "got": np.round(got, 6),
                     "want": np.round(want, 6), "pass": ok})

    # Spherical LAD must give G = 0.5 at nadir; this is the textbook anchor.
    check("G(0) spherical == 0.5", G_theta(0.0, 1.0), 0.5, tol=5e-4)

    # Eq 12 divided by cos(t) must equal Campbell's K. Guards the algebra.
    t = np.array([0.0, 15.0, 30.0, 45.0, 60.0, 75.0])
    for x in (1.0, 3.0):
        alt = np.sqrt(x**2 + np.tan(np.radians(t)) ** 2) / _campbell_denom(x)
        check(f"K identity, x={x:.0f}", K_theta(t, x), alt)

    # fAPAR limits. The printed form is what makes eq 8 wrong at L = 0.
    check("multiplicative fAPAR(L=0) == 0", ft04_fapar(0.0, 30.0, form="multiplicative"), 0.0)
    check("printed fAPAR(L=0) == -0.06", ft04_fapar(0.0, 30.0, form="printed"), PINF - 1.0, tol=1e-9)
    check("fAPAR(L=inf) -> Pinf", ft04_fapar(50.0, 30.0, form="multiplicative"), PINF, tol=1e-6)

    # Monotonicity: absorption rises with LAI and with SZA (longer path).
    lai = np.linspace(0, 6, 40)
    mono_l = np.all(np.diff(ft04_fapar(lai, 30.0)) > 0)
    rows.append({"check": "fAPAR increasing in LAI", "got": mono_l, "want": True, "pass": mono_l})
    z = np.linspace(0, 80, 40)
    mono_z = np.all(np.diff(ft04_fapar(3.0, z)) > 0)
    rows.append({"check": "fAPAR increasing in SZA", "got": mono_z, "want": True, "pass": mono_z})

    # Eq 3 sanity: no reflection, half the light transmitted -> fAPAR_T = 0.5.
    check("fAPAR_T eq3", fapar_total(1000.0, 500.0, 0.0), 0.5)

    res = pd.DataFrame(rows)
    if verbose:
        print(res.to_string(index=False))
        print(f"\n{int(res['pass'].sum())}/{len(res)} passed")
        # The LAD choice dominates the modelled SZA response. Printed so it can
        # never be defaulted silently: x=1 and x=3 disagree by a factor of ~4
        # in how much K grows from nadir to 75 degrees.
        for x in (1.0, 3.0):
            k = K_theta(np.array([0.0, 75.0]), x)
            print(f"  x={x:.0f}: K(0)={k[0]:.3f} K(75)={k[1]:.3f} ratio={k[1]/k[0]:.2f}")
    return res


if __name__ == "__main__":
    selftest()
