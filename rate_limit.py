from slowapi import Limiter
from slowapi.util import get_remote_address

from settings import get_settings

_cfg = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_cfg.rate_limit_default],
)

LOGIN_LIMIT    = _cfg.rate_limit_login
BULK_IMPORT_LIMIT = _cfg.rate_limit_bulk
ANALYSIS_LIMIT = _cfg.rate_limit_analysis
PAYMENT_LIMIT  = _cfg.rate_limit_payment
