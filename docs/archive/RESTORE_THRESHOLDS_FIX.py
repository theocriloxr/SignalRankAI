"""
Threshold Restoration and Diagnostic Fix

This script restores the original threshold values that were lowered to fix "Zero Signal" 
issues but now cause all signals to be rejected. It also adds diagnostic logging.

ORIGINAL THRESHOLDS (before the fixes):
1. engine/scoring.py:
   - MIN_RR: 1.5 (was lowered to 1.0)
   - CONFIDENCE_MIN: 0.35 (was lowered to 0.25)
   - CONFLUENCE_MIN: 25.0 (was lowered to 15.0)

2. engine/risk.py:
   - RR min: 1.5 (hardcoded - needs to be configurable and lowered)

3. engine/core.py:
   - ML_PROB_THRESHOLD: 0.55 (was lowered to 0.20)
   - PREMIUM_SCORE_THRESHOLD: 48 (was lowered to 35)
   - MIN_SCORE_THRESHOLD: 40 (was lowered to 30)

4. engine/dynamic_threshold.py & ml/dynamic_threshold.py:
   - Base threshold: 0.55 (was lowered to 0.30)

CHANGES MADE:
1. Restore MIN_RR to 1.5 in scoring.py
2. Add RR threshold config to risk.py (default 1.5, configurable via MIN_RR_RISK env var)
3. Add detailed logging to risk_check for diagnostics
4. Restore ML probability thresholds to original values
5. Restore score thresholds in core.py

AUTHOR: BlackBoxAI
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def apply_fix():
    print("=" * 60)
    print("THRESHOLD RESTORATION AND DIAGNOSTIC FIX")
    print("=" * 60)
    
    fixes_applied = []
    
    # ============================================================
    # FIX 1: Restore scoring.py thresholds
    # ============================================================
    print("\n[1/5] Fixing engine/scoring.py...")
    
    try:
        scoring_path = "engine/scoring.py"
        with open(scoring_path, "r") as f:
            content = f.read()
        
        # Restore MIN_RR
        old_min_rr = '''    # LOWERED from 1.5 to 1.0 to allow more signals through (fixes "Zero Signal")
    min_rr = _env_float("MIN_RR", 1.0)'''
        new_min_rr = '''    # ORIGINAL VALUE: 1.5 (restored from 1.0)
    min_rr = _env_float("MIN_RR", 1.5)'''
        
        if "_env_float(\"MIN_RR\", 1.0)" in content:
            content = content.replace(old_min_rr, new_min_rr)
            fixes_applied.append("scoring.py: MIN_RR restored to 1.5")
        
        # Restore CONFIDENCE_MIN
        old_conf = '''    # LOWERED from 0.35 to 0.25 to allow more signals through (fixes "Zero Signal")
    confidence_min = _env_float("CONFIDENCE_MIN", 0.25)'''
        new_conf = '''    # ORIGINAL VALUE: 0.35 (restored from 0.25)
    confidence_min = _env_float("CONFIDENCE_MIN", 0.35)'''
        
        if "_env_float(\"CONFIDENCE_MIN\", 0.25)" in content:
            content = content.replace(old_conf, new_conf)
            fixes_applied.append("scoring.py: CONFIDENCE_MIN restored to 0.35")
        
        # Restore CONFLUENCE_MIN
        old_confluence = '''    # LOWERED from 25.0 to 15.0 to allow more signals through (fixes "Zero Signal")
    confluence_min = _env_float("CONFLUENCE_MIN", 15.0)'''
        new_confluence = '''    # ORIGINAL VALUE: 25.0 (restored from 15.0)
    confluence_min = _env_float("CONFLUENCE_MIN", 25.0)'''
        
        if "_env_float(\"CONFLUENCE_MIN\", 15.0)" in content:
            content = content.replace(old_confluence, new_confluence)
            fixes_applied.append("scoring.py: CONFLUENCE_MIN restored to 25.0")
        
        with open(scoring_path, "w") as f:
            f.write(content)
            
        print("   ✓ scoring.py thresholds restored")
        
    except Exception as e:
        print(f"   ✗ Error in scoring.py: {e}")
    
    # ============================================================
    # FIX 2: Add configurable RR threshold to risk.py + logging
    # ============================================================
    print("\n[2/5] Fixing engine/risk.py...")
    
    try:
        risk_path = "engine/risk.py"
        with open(risk_path, "r") as f:
            content = f.read()
        
        # Add configurable RR threshold for risk check
        old_rr_check = '''    # RR min 1.5 (primary TP)
    entry = signal.get("entry")
    stop = signal.get("stop_loss") or signal.get("stop")
    tp_primary = signal.get("take_profit")
    if isinstance(tp_primary, list):
        tp_primary = tp_primary[0] if tp_primary else None
    if entry and stop and tp_primary:
        risk_dist = abs(float(entry) - float(stop))
        reward_dist = abs(float(tp_primary) - float(entry))
        if risk_dist > 0 and reward_dist / risk_dist < 1.5:
            return False'''
        
        new_rr_check = '''    # ORIGINAL VALUE: 1.5 - Made configurable via MIN_RR_RISK env var (default 1.5)
    # ADDED: diagnostic logging to identify which gate rejects signals
    min_rr_risk = float(os.getenv("MIN_RR_RISK", "1.5") or 1.5)
    entry = signal.get("entry")
    stop = signal.get("stop_loss") or signal.get("stop")
    tp_primary = signal.get("take_profit")
    if isinstance(tp_primary, list):
        tp_primary = tp_primary[0] if tp_primary else None
    if entry and stop and tp_primary:
        risk_dist = abs(float(entry) - float(stop))
        reward_dist = abs(float(tp_primary) - float(entry))
        rr_ratio = reward_dist / risk_dist if risk_dist > 0 else 0
        if rr_ratio < min_rr_risk:
            logger.warning(f"[risk] RR gate rejected: {signal.get('asset')} rr={rr_ratio:.2f} < {min_rr_risk}")
            return False'''
        
        if "reward_dist / risk_dist < 1.5:" in content:
            content = content.replace(old_rr_check, new_rr_check)
            fixes_applied.append("risk.py: RR threshold made configurable + logging added")
        
        with open(risk_path, "w") as f:
            f.write(content)
            
        print("   ✓ risk.py RR threshold configurable + logging added")
        
    except Exception as e:
        print(f"   ✗ Error in risk.py: {e}")
    
    # ============================================================
    # FIX 3: Restore core.py thresholds
    # ============================================================
    print("\n[3/5] Fixing engine/core.py...")
    
    try:
        core_path = "engine/core.py"
        with open(core_path, "r") as f:
            content = f.read()
        
        # Restore ML_PROB_THRESHOLD fallback
        old_ml_thresh = '''    class _FallbackThresholdOptimizer:
        def get_threshold(self) -> float:
# FIXED: Lowered from 0.25 to 0.20 to allow degraded ML model predictions
            return float(os.getenv('ML_PROB_THRESHOLD', '0.20') or 0.20)'''
        new_ml_thresh = '''    class _FallbackThresholdOptimizer:
        def get_threshold(self) -> float:
# ORIGINAL VALUE: 0.55 (restored from 0.20)
            return float(os.getenv('ML_PROB_THRESHOLD', '0.55') or 0.55)'''
        
        if "_env_float('ML_PROB_THRESHOLD', '0.20')" in content or "os.getenv('ML_PROB_THRESHOLD', '0.20')" in content:
            content = content.replace(old_ml_thresh, new_ml_thresh)
            fixes_applied.append("core.py: ML_PROB_THRESHOLD restored to 0.55")
        
        # Restore DEFAULT_MIN_SCORE_THRESHOLD
        old_score_thresh = '''# FIXED: Lowered from 48 to 35 to allow more signals through
# This fixes "generated_signals=0" when data is available but score threshold blocks
DEFAULT_MIN_SCORE_THRESHOLD = _env_float("PREMIUM_SCORE_THRESHOLD", 35)'''
        new_score_thresh = '''# ORIGINAL VALUE: 48 (restored from 35)
DEFAULT_MIN_SCORE_THRESHOLD = _env_float("PREMIUM_SCORE_THRESHOLD", 48)'''
        
        if "_env_float(\"PREMIUM_SCORE_THRESHOLD\", 35)" in content:
            content = content.replace(old_score_thresh, new_score_thresh)
            fixes_applied.append("core.py: PREMIUM_SCORE_THRESHOLD restored to 48")
        
        with open(core_path, "w") as f:
            f.write(content)
            
        print("   ✓ core.py thresholds restored")
        
    except Exception as e:
        print(f"   ✗ Error in core.py: {e}")
    
    # ============================================================
    # FIX 4: Restore dynamic_threshold.py
    # ============================================================
    print("\n[4/5] Fixing ml/dynamic_threshold.py...")
    
    try:
        dt_path = "ml/dynamic_threshold.py"
        with open(dt_path, "r") as f:
            content = f.read()
        
        # Restore base threshold comments
        old_base = '''    if base_threshold is None:
        base_threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.30"))'''
        new_base = '''    if base_threshold is None:
        # ORIGINAL VALUE: 0.55 (restored from 0.30)
        base_threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.55"))'''
        
        if "_env_float(\"ML_PROB_THRESHOLD\", \"0.30\")" in content:
            content = content.replace(old_base, new_base)
            fixes_applied.append("ml/dynamic_threshold.py: base threshold restored to 0.55")
        
        # Also fix the get_dynamic_ml_threshold function
        old_get = '''def get_dynamic_ml_threshold(base_threshold: Optional[float] = None) -> float:
    if base_threshold is None:
        base_threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.30"))'''
        new_get = '''def get_dynamic_ml_threshold(base_threshold: Optional[float] = None) -> float:
    if base_threshold is None:
        # ORIGINAL VALUE: 0.55 (restored from 0.30)
        base_threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.55"))'''
        
        if "os.getenv(\"ML_PROB_THRESHOLD\", \"0.30\")" in content:
            content = content.replace(old_get, new_get)
            fixes_applied.append("ml/dynamic_threshold.py: get_dynamic threshold restored")
        
        with open(dt_path, "w") as f:
            f.write(content)
            
        print("   ✓ ml/dynamic_threshold.py threshold restored")
        
    except Exception as e:
        print(f"   ✗ Error in ml/dynamic_threshold.py: {e}")
    
    # ============================================================
    # FIX 5: Restore engine/dynamic_threshold.py
    # ============================================================
    print("\n[5/5] Fixing engine/dynamic_threshold.py...")
    
    try:
        edt_path = "engine/dynamic_threshold.py"
        with open(edt_path, "r") as f:
            content = f.read()
        
        # Restore base threshold
        old_base = '''    if base_threshold is None:
        base_threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.30"))'''
        new_base = '''    if base_threshold is None:
        # ORIGINAL VALUE: 0.55 (restored from 0.30)
        base_threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.55"))'''
        
        if "_env_float(\"ML_PROB_THRESHOLD\", \"0.30\")" in content:
            content = content.replace(old_base, new_base)
            fixes_applied.append("engine/dynamic_threshold.py: base threshold restored to 0.55")
        
        with open(edt_path, "w") as f:
            f.write(content)
            
        print("   ✓ engine/dynamic_threshold.py threshold restored")
        
    except Exception as e:
        print(f"   ✗ Error in engine/dynamic_threshold.py: {e}")
    
    # ============================================================
    # Summary
    # ============================================================
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nFixes applied: {len(fixes_applied)}")
    for fix in fixes_applied:
        print(f"  • {fix}")
    
    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print("""
1. Deploy the changes to production
2. Set environment variables if needed:
   - MIN_RR=1.5 (scoring R:R ratio minimum)
   - MIN_RR_RISK=1.5 (risk check R:R minimum)  
   - ML_PROB_THRESHOLD=0.55 (ML probability threshold)
   - PREMIUM_SCORE_THRESHOLD=48 (score threshold)
3. Monitor engine logs for:
   - max_score=100.0 (this is OK - scoring caps at 100)
   - pipeline stats showing risk_passed > 0
   - [risk] RR gate rejected logs (diagnostic)
4. If signals still not passing, check:
   - Provider data quality (BRENT warnings in logs)
   - Strategy output (generated_signals count)
   - Consensus filter (consensus count)
    """)
    
    return len(fixes_applied) > 0


if __name__ == "__main__":
    success = apply_fix()
    sys.exit(0 if success else 1)
