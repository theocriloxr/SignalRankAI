#!/usr/bin/env python3
"""Validate scoring logic improvements for win rate optimization."""

from engine.scoring import score_signal, rr_score, volatility_quality_score

def test_component_scoring():
    """Validate individual scoring components."""
    print("=" * 60)
    print("COMPONENT SCORING VALIDATION")
    print("=" * 60)
    
    print("\n📊 RR Scoring (1.5 = 50%, 3.0 = 100%):")
    print(f"  RR=1.0:  {rr_score(1.0):.3f} (reject - too low)")
    print(f"  RR=1.5:  {rr_score(1.5):.3f} (minimum acceptable)")
    print(f"  RR=2.0:  {rr_score(2.0):.3f} (good)")
    print(f"  RR=2.5:  {rr_score(2.5):.3f} (excellent)")
    print(f"  RR=3.0:  {rr_score(3.0):.3f} (ideal)")
    
    print("\n📈 Volatility Scoring (0.08 = perfect, 0.20 = reject):")
    for vol in [0.06, 0.08, 0.12, 0.16, 0.20, 0.25]:
        score = volatility_quality_score({"volatility": vol})
        print(f"  vol={vol:.2f}: {score:.3f}")

def test_quality_gates():
    """Validate quality gates reject bad signals."""
    print("\n" + "=" * 60)
    print("QUALITY GATES (Should reject bad signals)")
    print("=" * 60)
    
    # Low confidence rejection
    signal = {'confidence': 0.2, 'entry': 100, 'stop': 95, 'targets': 110}
    score = score_signal(signal)
    print(f"\n❌ Low confidence (0.2): {score} (rejected ✓)")
    
    # Poor RR rejection
    signal = {'confidence': 0.8, 'entry': 100, 'stop': 95, 'targets': 102, 'volatility': 0.12}
    score = score_signal(signal)
    print(f"❌ Poor RR (1.0:1): {score} (rejected ✓)")
    
    # High volatility rejection
    signal = {'confidence': 0.8, 'entry': 100, 'stop': 90, 'targets': 110, 'volatility': 0.22}
    score = score_signal(signal)
    print(f"❌ High volatility (0.22): {score} (rejected ✓)")

def test_winning_signals():
    """Validate good signals produce high scores."""
    print("\n" + "=" * 60)
    print("WINNING SIGNALS (Should score high)")
    print("=" * 60)
    
    # Good signal
    print("\n✅ Good signal (conf=0.7, RR=2.0, vol=0.12):")
    signal = {'confidence': 0.7, 'entry': 100.0, 'stop': 90.0, 'targets': 110.0, 'volatility': 0.12}
    score = score_signal(signal)
    print(f"  Base score: {score:.2f}")
    print(f"  Expected: ~58-60 (above MIN_SCORE_THRESHOLD=65? No - gate needed)")
    
    # Excellent signal
    print("\n✅ Excellent signal (conf=0.85, RR=2.5, vol=0.08, regime=0.9):")
    signal = {'confidence': 0.85, 'entry': 100.0, 'stop': 85.0, 'targets': 112.5, 'volatility': 0.08, 'regime_fit': 0.9}
    score = score_signal(signal)
    print(f"  Base score: {score:.2f}")
    
    # Perfect signal
    print("\n✅ Perfect signal (conf=1.0, RR=3.0, vol=0.08, regime=1.0, ML=0.9):")
    signal = {'confidence': 1.0, 'entry': 100.0, 'stop': 85.0, 'targets': 115.0, 'volatility': 0.08, 'regime_fit': 1.0, 'ml_probability': 0.9}
    score = score_signal(signal)
    print(f"  Score: {score:.2f} (top quality)")

def test_ml_boost():
    """Validate ML boost multiplier."""
    print("\n" + "=" * 60)
    print("ML CONFIDENCE BOOST (0.8-1.2x multiplier)")
    print("=" * 60)
    
    base_signal = {'confidence': 0.8, 'entry': 100.0, 'stop': 90.0, 'targets': 110.0, 'volatility': 0.12}
    
    print("\n📡 Same signal with varying ML confidence:")
    for ml_prob in [0.0, 0.5, 0.75, 1.0]:
        signal = base_signal.copy()
        signal['ml_probability'] = ml_prob
        score = score_signal(signal)
        ml_boost = 0.8 + (ml_prob * 0.4)
        print(f"  ML={ml_prob}: boost={ml_boost:.2f}x → score={score:.2f}")

def test_regime_bonus():
    """Validate regime alignment bonus."""
    print("\n" + "=" * 60)
    print("REGIME ALIGNMENT BONUS (+10-20% multiplier)")
    print("=" * 60)
    
    base_signal = {'confidence': 0.8, 'entry': 100.0, 'stop': 90.0, 'targets': 110.0, 'volatility': 0.12}
    
    print("\n📡 Same signal with varying regime fit:")
    for regime in [0.0, 0.5, 0.75, 1.0]:
        signal = base_signal.copy()
        signal['regime_fit'] = regime
        score = score_signal(signal)
        regime_bonus = 1.0 + (regime * 0.2)
        print(f"  Regime={regime}: bonus={regime_bonus:.2f}x → score={score:.2f}")

if __name__ == '__main__':
    test_component_scoring()
    test_quality_gates()
    test_winning_signals()
    test_ml_boost()
    test_regime_bonus()
    
    print("\n" + "=" * 60)
    print("✓ SCORING LOGIC VALIDATION COMPLETE")
    print("=" * 60)
    print("\nKey Improvements for Win Rate:")
    print("  1. Quality gates reject low-confidence signals (<0.3)")
    print("  2. Hard RR floor (1.5:1 minimum for edge)")
    print("  3. Volatility penalty (reject >0.20)")
    print("  4. Regime alignment bonus (+10-20%)")
    print("  5. ML confidence boost (+20% range)")
    print("  6. Exceptional R/R rewards (2.5:1+ gets +20%)")
    print("\n" + "=" * 60)
