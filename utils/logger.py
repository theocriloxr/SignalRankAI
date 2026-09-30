import logging
import structlog
from utils.context import get_correlation_id

def setup_structlog():
    """Configure structlog globally with correlation ID injection."""
    
    def add_correlation_id(logger, method_name, event_dict):
        """Add correlation_id to log event if available."""
        corr_id = get_correlation_id()
        if corr_id:
            event_dict["correlation_id"] = corr_id
        return event_dict
        
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            add_correlation_id,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Optional: configure stdlib logging to format nicely
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )
