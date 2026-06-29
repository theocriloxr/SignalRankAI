"""
Event type constants for the SignalRankAI Event Bus.

Defines all event types used in the system for type safety and documentation.
"""

# Signal Events
SIGNAL_READY = "SIGNAL_READY"           # Signal generated and ready for delivery
SIGNAL_DELIVERED = "SIGNAL_DELIVERED"   # Signal successfully delivered to user
SIGNAL_FAILED = "SIGNAL_FAILED"        # Signal delivery failed
SIGNAL_EXPIRED = "SIGNAL_EXPIRED"       # Signal expired without execution

# Trade Events  
TRADE_OPENED = "TRADE_OPENED"           # Paper/live trade opened
TRADE_CLOSED = "TRADE_CLOSED"           # Paper/live trade closed
TRADE_SL_HIT = "TRADE_SL_HIT"           # Stop loss hit
TRADE_TP_HIT = "TRADE_TP_HIT"           # Take profit hit

# System Events
SYSTEM_HEALTHY = "SYSTEM_HEALTHY"       # System health check passed
SYSTEM_UNHEALTHY = "SYSTEM_UNHEALTHY"    # System health check failed
PROVIDER_SWITCHED = "PROVIDER_SWITCHED"  # Data provider switched

# ML Events
ML_PREDICTION = "ML_PREDICTION"         # ML model made a prediction
ML_RETRAIN = "ML_RETRAIN"              # Trigger ML model retraining
ML_DRIFT_DETECTED = "ML_DRIFT_DETECTED" # Model drift detected

# Priority levels (higher = more urgent)
PRIORITY_CRITICAL = 100    # System-critical events
PRIORITY_VIP = 90         # VIP signal delivery
PRIORITY_HIGH = 75       # High-priority signals
PRIORITY_NORMAL = 50      # Normal signal delivery
PRIORITY_LOW = 25         # Low-priority events
PRIORITY_BATCH = 10       # Batch processing

# Event type to priority mapping
EVENT_PRIORITIES = {
    SIGNAL_READY: PRIORITY_VIP,
    SIGNAL_DELIVERED: PRIORITY_NORMAL,
    SIGNAL_FAILED: PRIORITY_HIGH,
    SIGNAL_EXPIRED: PRIORITY_LOW,
    TRADE_OPENED: PRIORITY_HIGH,
    TRADE_CLOSED: PRIORITY_NORMAL,
    TRADE_SL_HIT: PRIORITY_CRITICAL,
    TRADE_TP_HIT: PRIORITY_CRITICAL,
    SYSTEM_HEALTHY: PRIORITY_LOW,
    SYSTEM_UNHEALTHY: PRIORITY_CRITICAL,
    PROVIDER_SWITCHED: PRIORITY_HIGH,
    ML_PREDICTION: PRIORITY_LOW,
    ML_RETRAIN: PRIORITY_BATCH,
    ML_DRIFT_DETECTED: PRIORITY_HIGH,
}

# Channels for Redis pub/sub
CHANNEL_SIGNALS = "signalrank:signals"
CHANNEL_TRADES = "signalrank:trades"
CHANNEL_SYSTEM = "signalrank:system"
CHANNEL_ML = "signalrank:ml"

# Stream consumer groups
CONSUMER_GROUP_ENGINE = "engine_group"
CONSUMER_GROUP_BROADCASTER = "broadcaster_group"
CONSUMER_GROUP_WORKER = "worker_group"
