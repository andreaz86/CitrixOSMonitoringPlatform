import requests
import time
import json
from datetime import datetime, timedelta

from utils import config
from utils.retry import retry_with_backoff
from database.postgres_client import postgres_manager

class CitrixAuthManager:
    def __init__(self):
        self.client_id = config.CITRIX_CLIENT_ID
        self.client_secret = config.CITRIX_CLIENT_SECRET
        self.auth_url = config.CITRIX_AUTH_URL
        self.token = None
        self.token_expiry = None
        # Add buffer time to refresh token (5 minutes before expiration)
        self.expiry_buffer = 300
        
        if config.DEBUG:
            config.logger.debug(f"CitrixAuthManager initialized with auth URL: {self.auth_url}")
            config.logger.debug(f"Token expiry buffer set to {self.expiry_buffer} seconds")
            
        # Tenta di recuperare il token dal database all'inizializzazione
        self._load_token_from_db()
    
    def _load_token_from_db(self):
        """Carica un token valido dal database se disponibile."""
        token, expiry = postgres_manager.get_auth_token()
        if token and expiry:
            self.token = token
            self.token_expiry = expiry
            if config.DEBUG:
                time_to_expiry = (self.token_expiry - datetime.now()).total_seconds()
                config.logger.debug(f"Token recuperato dal database, valido per altri {time_to_expiry:.1f} secondi")
            return True
        return False

    @retry_with_backoff()
    def get_new_token(self):
        """
        Get a new bearer token from Citrix Cloud API.
        """
        config.logger.info("Requesting new Citrix Cloud API token")
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        payload = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        if config.DEBUG:
            config.logger.debug(f"Auth request URL: {self.auth_url}")
            config.logger.debug(f"Auth request headers: {headers}")
            # Logging payload without secrets for security
            safe_payload = payload.copy()
            safe_payload['client_id'] = safe_payload['client_id'][:5] + '...' if safe_payload['client_id'] else None
            safe_payload['client_secret'] = '[REDACTED]'
            config.logger.debug(f"Auth request payload (sanitized): {safe_payload}")
        
        start_time = time.time()
        
        try:
            response = requests.post(self.auth_url, headers=headers, data=payload)
            
            if config.DEBUG:
                config.logger.debug(f"Auth response status code: {response.status_code}")
                config.logger.debug(f"Auth response headers: {response.headers}")
                
            response.raise_for_status()
            
            token_data = response.json()
            self.token = token_data['access_token']
            
            # Calculate token expiry time (default to 1 hour if not specified)
            expires_in = token_data.get('expires_in', 3600)
            try:
                expires_in = int(expires_in)
            except (ValueError, TypeError):
                config.logger.warning("Invalid 'expires_in' value, defaulting to 3600 seconds")
                expires_in = 3600
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
            
            # Salva il token nel database
            postgres_manager.store_auth_token(self.token, self.token_expiry)
            
            if config.DEBUG:
                # Don't log the full token for security reasons
                token_preview = self.token[:10] + '...' if self.token else None
                config.logger.debug(f"Token acquired (first 10 chars): {token_preview}")
                config.logger.debug(f"Token expires in {expires_in} seconds")
                config.logger.debug(f"Token expiry timestamp: {self.token_expiry}")
                
            config.logger.info(f"New token acquired, expires at {self.token_expiry}")
            return self.token
        except Exception as e:
            config.logger.error(f"Failed to get token: {str(e)}")
            if config.DEBUG and hasattr(e, 'response') and e.response is not None:
                config.logger.debug(f"Auth error response status: {e.response.status_code}")
                config.logger.debug(f"Auth error response content: {e.response.content.decode('utf-8')}")
            raise
        finally:
            if config.DEBUG:
                duration = time.time() - start_time
                config.logger.debug(f"Auth request duration: {duration:.3f} seconds")

    def get_token(self):
        """
        Get a valid bearer token, reusing existing one if valid, or acquiring new one if needed.
        """
        # If no token exists or token is about to expire, get a new one
        if (not self.token or not self.token_expiry or 
            datetime.now() > (self.token_expiry - timedelta(seconds=self.expiry_buffer))):
            if config.DEBUG:
                if not self.token:
                    config.logger.debug("No existing token, requesting new one")
                elif not self.token_expiry:
                    config.logger.debug("Token expiry not set, requesting new token")
                else:
                    time_to_expiry = (self.token_expiry - datetime.now()).total_seconds()
                    config.logger.debug(f"Token expires in {time_to_expiry:.1f} seconds, refreshing token")
            return self.get_new_token()
        
        if config.DEBUG:
            time_to_expiry = (self.token_expiry - datetime.now()).total_seconds()
            config.logger.debug(f"Reusing existing token, valid for {time_to_expiry:.1f} more seconds")
        else:
            config.logger.debug("Reusing existing token")
        
        return self.token

    def get_auth_header(self):
        """
        Return the authorization header with a valid token.
        """
        token = self.get_token()
        return {'Authorization': f'CwsAuth bearer={token}'}

# Create a singleton instance of the auth manager
auth_manager = CitrixAuthManager()