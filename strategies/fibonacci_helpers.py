from typing import Tuple


def is_price_in_golden_pocket(price: float, swing_high: float, swing_low: float, tol_pct: float = 0.0001) -> bool:
    """Return True if `price` lies inside the Golden Pocket (0.618-0.786) for the given swing.

    Tolerance `tol_pct` is a fractional tolerance (e.g., 0.0001 == 0.01%).
    """
    try:
        if swing_high <= swing_low:
            return False
        pocket_low = swing_high - ((swing_high - swing_low) * 0.618)
        pocket_high = swing_high - ((swing_high - swing_low) * 0.786)
        low = min(pocket_low, pocket_high)
        high = max(pocket_low, pocket_high)
        if low <= price <= high:
            return True
        # tolerance around boundaries
        tol = max(abs(price) * float(tol_pct or 0.0), 1e-12)
        if abs(price - low) <= tol or abs(price - high) <= tol:
            return True
        return False
    except Exception:
        return False
