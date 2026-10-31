"""
TLEService: everything to do with a raw two-line element set. Pure functions,
no I/O.

What this module actually computes (stated precisely, because the papers
describe it):

  * Pathway 1 -- the six mean orbital elements ENCODED in the TLE: inclination,
    eccentricity, RAAN, argument of perigee, mean anomaly, mean motion. These are
    read with the `sgp4` library's TLE parser (Satrec.twoline2rv), which is the
    reference implementation of the TLE format. No propagation is performed.
  * Pathway 2 -- five quantities DERIVED ANALYTICALLY from the mean motion using
    two-body (Keplerian) relations: semi-major axis, mean altitude above the
    equatorial radius, circular orbital velocity, orbital period, and specific
    orbital energy. Note all five are functions of mean motion alone.

This module does NOT propagate orbits (no trajectory prediction) and does NOT
classify (that is ClassificationService's job).

If `sgp4` isn't installed, the same six elements are decoded directly from the
TLE's fixed columns; the resulting values are identical.
"""
import math
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from sgp4.api import Satrec
    _SGP4_AVAILABLE = True
except ImportError:
    _SGP4_AVAILABLE = False

MU_EARTH = 398600.4418        # km^3/s^2
EARTH_RADIUS_KM = 6378.137    # km

_TLE_LINE_RE = re.compile(r"^[12] .{67}$")  # a TLE line is 69 characters total, starts with its line number

# Alpha-5: catalogue numbers above 99999 replace the first digit with a letter
# (A=10 ... Z=33, skipping I and O).
_ALPHA5_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


# --------------------------------------------------------------------------- #
#  Input cleaning / detection                                                  #
# --------------------------------------------------------------------------- #
def clean_tle_line(line: Optional[str]) -> str:
    """Strips Windows line endings and trailing/leading whitespace that a
    copy-paste commonly adds. Internal spacing (which is significant) is kept."""
    if line is None:
        return ""
    return line.replace("\r", "").strip()


def looks_like_tle(text: str) -> Optional[Tuple[str, str]]:
    """If `text` contains two TLE-shaped lines, return them as (line1, line2)."""
    if not text:
        return None
    lines = [clean_tle_line(ln) for ln in text.splitlines() if ln.strip()]
    line1 = next((ln for ln in lines if ln.startswith("1 ") and len(ln) >= 60), None)
    line2 = next((ln for ln in lines if ln.startswith("2 ") and len(ln) >= 60), None)
    if line1 and line2:
        return line1, line2
    return None


_NUMBER_RE = re.compile(r"\d+")
_PREFIX_RE = re.compile(
    r"(?:norad|catalog(?:ue)?|cat|sat(?:ellite)?|object|id|no\.?|number|#)\s*[:#.]?\s*(?:id|no\.?|number|#)?\s*[:#]?\s*$",
    re.IGNORECASE,
)


def find_norad_ids(text: str) -> List[str]:
    """Extracts NORAD catalogue IDs from free text, in order, de-duplicated.

    Rules (transparent, no guessing):
      * A number directly preceded by a keyword ("NORAD", "ID", "#", "catalog",
        ...) is always taken, whatever its length -- so "NORAD 5" works.
      * An unlabelled number is taken only if it has 3-9 digits and is not a
        plausible year (1957-2100), and is not part of a decimal, date or
        international designator (e.g. "1998-067A", "51.64").
    """
    if not text:
        return []
    found: List[str] = []
    for m in _NUMBER_RE.finditer(text):
        digits = m.group(0)
        start, end = m.start(), m.end()
        before = text[start - 1] if start > 0 else " "
        after = text[end] if end < len(text) else " "
        if before in ".-/:" or after in ".-/" or before.isalpha() or after.isalpha():
            # part of a decimal, date, designator, or an alphanumeric token
            # (exception: "#123" / "id:123" handled by the prefix check below)
            if not (before in ":" and _PREFIX_RE.search(text[max(0, start - 20):start])):
                continue
        if len(digits) > 9:
            continue
        labelled = bool(_PREFIX_RE.search(text[max(0, start - 24):start]))
        value = int(digits)
        if value <= 0:
            continue
        if not labelled:
            if len(digits) < 3:
                continue
            if len(digits) == 4 and 1957 <= value <= 2100:
                continue
        norm = str(value)
        if norm not in found:
            found.append(norm)
    return found


# --------------------------------------------------------------------------- #
#  Validation                                                                  #
# --------------------------------------------------------------------------- #
def _tle_checksum_valid(line: str) -> bool:
    """Last character = (sum of digits, '-' counts as 1) mod 10."""
    if len(line) < 69:
        return False
    body, checksum_char = line[:68], line[68]
    if not checksum_char.isdigit():
        return False
    total = 0
    for ch in body:
        if ch.isdigit():
            total += int(ch)
        elif ch == "-":
            total += 1
    return total % 10 == int(checksum_char)


def validate_tle(line1: str, line2: str) -> Tuple[bool, Optional[str]]:
    """Structural validation. Returns (is_valid, error_message). Lines are
    cleaned first, so pass the same cleaned lines to extract_orbital_parameters()."""
    line1, line2 = clean_tle_line(line1), clean_tle_line(line2)
    if not _TLE_LINE_RE.match(line1):
        return False, f"Line 1 is malformed (expected 69 characters starting with '1 '); got {len(line1)} characters."
    if not _TLE_LINE_RE.match(line2):
        return False, f"Line 2 is malformed (expected 69 characters starting with '2 '); got {len(line2)} characters."
    if not _tle_checksum_valid(line1):
        return False, "Line 1 checksum does not match its contents -- the TLE may be corrupted or mistyped."
    if not _tle_checksum_valid(line2):
        return False, "Line 2 checksum does not match its contents -- the TLE may be corrupted or mistyped."
    norad1 = line1[2:7].strip()
    norad2 = line2[2:7].strip()
    if norad1 != norad2:
        return False, f"Line 1 and Line 2 disagree on NORAD ID ({norad1} vs {norad2}) -- these two lines may not belong together."
    return True, None


def extract_norad_id(line1: str) -> Optional[str]:
    """NORAD ID from TLE line 1, including Alpha-5 encoded IDs (> 99999)."""
    raw = clean_tle_line(line1)[2:7]
    if len(raw) != 5:
        return None
    if raw.strip().isdigit():
        return str(int(raw))                      # "00544" -> "544"
    first, rest = raw[0].upper(), raw[1:]
    if first in _ALPHA5_LETTERS and rest.isdigit():
        return str((_ALPHA5_LETTERS.index(first) + 10) * 10000 + int(rest))
    return None


# --------------------------------------------------------------------------- #
#  Feature extraction                                                          #
# --------------------------------------------------------------------------- #
def _derive_from_mean_elements(inclination_deg, eccentricity, raan_deg, arg_perigee_deg,
                                mean_anomaly_deg, mean_motion_rev_per_day) -> Dict[str, float]:
    """Pathway 2: two-body relations from mean motion (see module docstring)."""
    n_rad_per_sec = mean_motion_rev_per_day * 2 * math.pi / 86400.0
    semi_major_axis_km = (MU_EARTH / (n_rad_per_sec ** 2)) ** (1.0 / 3.0)
    altitude_km = semi_major_axis_km - EARTH_RADIUS_KM                  # mean altitude, not perigee
    orbital_velocity_km_s = math.sqrt(MU_EARTH / semi_major_axis_km)    # circular-orbit approximation
    orbital_period_min = 2 * math.pi * math.sqrt(semi_major_axis_km ** 3 / MU_EARTH) / 60.0
    specific_orbital_energy_km2_s2 = -MU_EARTH / (2 * semi_major_axis_km)
    return {
        "inclination_deg": inclination_deg,
        "eccentricity": eccentricity,
        "raan_deg": raan_deg,
        "arg_perigee_deg": arg_perigee_deg,
        "mean_anomaly_deg": mean_anomaly_deg,
        "mean_motion_rev_per_day": mean_motion_rev_per_day,
        "semi_major_axis_km": semi_major_axis_km,
        "altitude_km": altitude_km,
        "orbital_velocity_km_s": orbital_velocity_km_s,
        "orbital_period_min": orbital_period_min,
        "specific_orbital_energy_km2_s2": specific_orbital_energy_km2_s2,
    }


def _extract_via_sgp4_parser(line1: str, line2: str) -> Dict[str, float]:
    sat = Satrec.twoline2rv(line1, line2)
    return _derive_from_mean_elements(
        inclination_deg=math.degrees(sat.inclo),
        eccentricity=sat.ecco,
        raan_deg=math.degrees(sat.nodeo),
        arg_perigee_deg=math.degrees(sat.argpo),
        mean_anomaly_deg=math.degrees(sat.mo),
        mean_motion_rev_per_day=sat.no_kozai * 1440.0 / (2 * math.pi),
    )


def _extract_via_direct_decode(line1: str, line2: str) -> Dict[str, float]:
    """Fallback if `sgp4` isn't installed: the six mean elements sit at fixed
    columns of line 2 (standard TLE format)."""
    inclination_deg = float(line2[8:16])
    raan_deg = float(line2[17:25])
    eccentricity = float("0." + line2[26:33].strip())
    arg_perigee_deg = float(line2[34:42])
    mean_anomaly_deg = float(line2[43:51])
    mean_motion_rev_per_day = float(line2[52:63])
    return _derive_from_mean_elements(
        inclination_deg, eccentricity, raan_deg, arg_perigee_deg,
        mean_anomaly_deg, mean_motion_rev_per_day,
    )


def extract_orbital_parameters(line1: str, line2: str) -> Dict[str, Any]:
    """Returns the 11 orbital features, plus `_extraction_method` for transparency."""
    line1, line2 = clean_tle_line(line1), clean_tle_line(line2)
    if _SGP4_AVAILABLE:
        try:
            params = _extract_via_sgp4_parser(line1, line2)
            params["_extraction_method"] = "sgp4_tle_parser"
            return params
        except Exception as e:
            print(f"[TLEService] sgp4 parsing failed ({e}); falling back to direct decode.")
    params = _extract_via_direct_decode(line1, line2)
    params["_extraction_method"] = "direct_tle_decode"
    return params
