import time
import functools
import requests
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type, RetryError

from utils import config

def retry_with_backoff(max_retries=None, backoff_factor=None, max_wait=None):
    """
    Decorator for retrying API calls with exponential backoff.
    
    Args:
        max_retries: Maximum number of retries
        backoff_factor: Factor for exponential backoff
        max_wait: Maximum wait time between retries in seconds
    """
    max_retries = max_retries or config.MAX_RETRIES
    backoff_factor = backoff_factor or config.RETRY_BACKOFF_FACTOR
    max_wait = max_wait or config.RETRY_MAX_WAIT
    
    def decorator(func):
        @retry(
            retry=retry_if_exception_type((
                requests.exceptions.RequestException,
                requests.exceptions.HTTPError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout
            )),
            wait=wait_exponential(multiplier=backoff_factor, max=max_wait),
            stop=stop_after_attempt(max_retries),
            reraise=True,
        )
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except RetryError as e:
                config.logger.error(f"Failed after {max_retries} retries: {str(e.last_attempt.exception())}")
                raise e.last_attempt.exception()
            except Exception as e:
                config.logger.error(f"Error during execution: {str(e)}")
                raise
        return wrapper
    return decorator