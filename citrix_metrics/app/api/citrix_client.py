import requests
from datetime import datetime, timedelta
import time
import json
import os
import yaml

from utils import config
from utils.auth import auth_manager
from utils.retry import retry_with_backoff
from utils.prometheus_metrics import API_REQUESTS, API_LATENCY

class CitrixAPIClient:
    def __init__(self):
        self.base_url = config.CITRIX_API_BASE_URL
        self.customer_id = config.CITRIX_CUSTOMER_ID
        self.auth_manager = auth_manager
        # Setup proxy configuration
        self.proxies = self._setup_proxies()
        
        # Initialize site_id as None, will be set later
        self.site_id = None
        
        # Carica le configurazioni delle API da file
        self.api_configs = self._load_api_configs()
        
        if config.DEBUG:
            config.logger.debug(f"CitrixAPIClient initialized with base URL: {self.base_url}")
            config.logger.debug(f"Customer ID: {self.customer_id}")
            if self.api_configs:
                config.logger.debug(f"Loaded {len(self.api_configs)} API configurations")
            
    def _setup_proxies(self):
        """Configure proxies from environment variables."""
        proxies = {}
        
        # Check for proxy environment variables (uppercase first, then lowercase)
        if config.HTTP_PROXY:
            proxies['http'] = config.HTTP_PROXY
        elif config.http_proxy:
            proxies['http'] = config.http_proxy
            
        if config.HTTPS_PROXY:
            proxies['https'] = config.HTTPS_PROXY
        elif config.https_proxy:
            proxies['https'] = config.https_proxy
            
        # Log proxy configuration
        if proxies:
            config.logger.info(f"Using proxy configuration: {proxies}")
            if config.DEBUG:
                config.logger.debug(f"Proxy details - HTTP: {proxies.get('http')}, HTTPS: {proxies.get('https')}")
        
        return proxies or None

    def _load_api_configs(self):
        """
        Carica le configurazioni delle API da un file YAML.
        
        Returns:
            dict: Configurazioni delle API
        """
        api_config_path = os.environ.get('API_CONFIG_PATH', '/etc/citrix_metrics/api_config.yaml')
        
        try:
            if os.path.exists(api_config_path):
                with open(api_config_path, 'r') as f:
                    configs = yaml.safe_load(f)
                    config.logger.info(f"Loaded API configurations from {api_config_path}")
                    return configs
            else:
                config.logger.warning(f"API configuration file {api_config_path} not found, using fallback configuration")
                return self._get_fallback_api_configs()
        except Exception as e:
            config.logger.error(f"Error loading API configurations: {str(e)}")
            return self._get_fallback_api_configs()
    
    def _get_fallback_api_configs(self):
        """
        Fornisce una configurazione di fallback per le API in caso di errore nel caricamento dal file.
        
        Returns:
            dict: Configurazioni di fallback per le API
        """
        return {
            "load_indexes": {
                "endpoint": "/monitorodata/LoadIndexes",
                "time_window": 5,
                "filter_field": "CreatedDate",
                "select": ["Id", "CreatedDate", "LifecycleState", "SessionId", "UserId", "DesktopGroupId", "Index", "LoadIndex"],
                "expand": {
                    "Machine": ["Id", "DnsName", "IPAddress", "AgentVersion"],
                    "Session": ["StartDate", "LogOnDuration", "ConnectionState"]
                },
                "order_by": "CreatedDate desc"
            },
            "machines": {
                "endpoint": "/monitorodata/Machines",
                "pagination": True
            }
        }

    def _get_headers(self, api_type=None):
        """
        Get API headers with authentication.
        
        Args:
            api_type (str, optional): Type of API ('rest' or None)
        
        Returns:
            dict: Headers dictionary
        """
        headers = self.auth_manager.get_auth_header()
        headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Citrix-CustomerId': self.customer_id
        })
        
        # Add Citrix-InstanceId header for REST API calls when site_id is available
        if api_type == 'rest' and self.site_id:
            headers['Citrix-InstanceId'] = self.site_id
            if config.DEBUG:
                config.logger.debug(f"Added Citrix-InstanceId header with site_id: {self.site_id}")
        
        if config.DEBUG:
            # In debug mode, log headers without auth token for security
            debug_headers = headers.copy()
            if 'Authorization' in debug_headers:
                debug_headers['Authorization'] = 'Bearer [REDACTED]'
            config.logger.debug(f"Request headers: {debug_headers}")
            
        return headers

    @retry_with_backoff()
    def _make_request(self, method, endpoint, params=None, data=None, use_query_string=False, api_type=None):
        """
        Make a HTTP request to the Citrix API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters (dict or string)
            data: Request body
            use_query_string: If True, params is treated as a full query string
            api_type: Type of API ('rest' or 'odata')
        """
        # Se use_query_string è True, i parametri sono già formattati come una stringa di query
        if use_query_string and params:
            url = f"{self.base_url}{endpoint}?{params}"
            params = None  
        else:
            url = f"{self.base_url}{endpoint}"
        
        headers = self._get_headers(api_type=api_type)
        
        # Basic logging for all modes
        config.logger.debug(f"Making {method} request to {url}")
        
        # Detailed logging in debug mode
        if config.DEBUG:
            config.logger.debug(f"Request URL: {url}")
            config.logger.debug(f"Request method: {method}")
            if params and not use_query_string:
                config.logger.debug(f"Request params: {json.dumps(params)}")
            if data:
                config.logger.debug(f"Request data: {json.dumps(data)}")
        
        # Track API request latency using Prometheus histogram
        start_time = time.time()
        status = "success"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=data,
                proxies=self.proxies
            )
            
            # Handle 401 separately to refresh token
            if response.status_code == 401:
                config.logger.warning("Authentication failed, requesting new token")
                # Force new token acquisition
                self.auth_manager.token = None
                headers = self._get_headers()
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=data,
                    proxies=self.proxies
                )
            
            if config.DEBUG:
                config.logger.debug(f"Response status code: {response.status_code}")
                config.logger.debug(f"Response headers: {response.headers}")
                if response.content:
                    # Limit response content logging to avoid excessive output
                    content_str = response.content.decode('utf-8')
                    if len(content_str) > 500:
                        config.logger.debug(f"Response content (truncated): {content_str[:500]}...")
                    else:
                        config.logger.debug(f"Response content: {content_str}")
            
            response.raise_for_status()
            return response.json() if response.content else None
            
        except requests.exceptions.RequestException as e:
            status = "error"
            config.logger.error(f"Request failed: {str(e)}")
            if config.DEBUG and hasattr(e, 'response') and e.response is not None:
                config.logger.debug(f"Error response status: {e.response.status_code}")
                config.logger.debug(f"Error response headers: {e.response.headers}")
                if e.response.content:
                    config.logger.debug(f"Error response content: {e.response.content.decode('utf-8')}")
            raise e
        finally:
            # Record duration and requests metrics
            duration = time.time() - start_time
            API_LATENCY.labels(endpoint=endpoint, method=method).observe(duration)
            API_REQUESTS.labels(endpoint=endpoint, method=method, status=status).inc()
            if config.DEBUG:
                config.logger.debug(f"Request duration: {duration:.3f} seconds")

    def get_with_pagination(self, endpoint, params=None, api_type=None):
        """
        Get all results from a paginated API endpoint using @odata.nextLink pattern or ContinuationToken.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            api_type: Type of API ('rest' or 'odata')
            
        Returns:
            List of all items from all pages
        """
        if params is None:
            params = {}
            
        # Initialize the list to store all items
        all_items = []
        current_url = endpoint
        is_first_request = True
        
        if config.DEBUG:
            config.logger.debug(f"Starting paginated request to {endpoint} with params {params}")
        
        while current_url:
            # For the first request, use the endpoint and params
            # For subsequent requests, handle based on API type
            if is_first_request:
                response_data = self._make_request('GET', current_url, params=params, api_type=api_type)
                is_first_request = False
            else:
                if api_type == 'rest':
                    # For REST APIs using ContinuationToken
                    if continuation_token:
                        # Reset the URL to the original endpoint and add the new token
                        current_url = endpoint
                        params = {'continuationtoken': continuation_token}
                        response_data = self._make_request('GET', current_url, params=params, api_type=api_type)
                    else:
                        break
                else:
                    # For OData APIs using nextLink
                    if current_url.startswith(self.base_url):
                        relative_url = current_url[len(self.base_url):]
                    else:
                        relative_url = current_url
                    response_data = self._make_request('GET', relative_url, use_query_string=True, api_type=api_type)
            
            # Check if response contains items based on API type
            if api_type == 'rest':
                # For REST APIs, check for ContinuationToken
                if isinstance(response_data, dict):
                    # Ensure response is in the expected format for postgres_client
                    if not ('Items' in response_data or 'value' in response_data):
                        # If response is a list or a dict without Items/value, wrap it
                        if isinstance(response_data, list):
                            response_data = {'Items': response_data}
                        else:
                            response_data = {'Items': [response_data]}
                    
                    # Extract items based on response structure
                    items = response_data.get('Items', []) or response_data.get('value', [])
                    if items and not isinstance(items, list):
                        items = [items]  # Convert single item to list
                    
                    all_items.extend(items)
                    
                    # Get continuation token for next request
                    continuation_token = response_data.get('ContinuationToken')
                    
                    if config.DEBUG:
                        config.logger.debug(f"Retrieved {len(items)} items from REST API")
                        if continuation_token:
                            config.logger.debug(f"Found ContinuationToken: {continuation_token}")
                    
                    # If no continuation token, we're done
                    if not continuation_token:
                        current_url = None
                else:
                    # If response is a list or single item, wrap it in the expected format
                    if isinstance(response_data, list):
                        all_items.extend(response_data)
                    else:
                        all_items.append(response_data)
                    current_url = None
            else:
                # For OData APIs, check for @odata.nextLink
                if isinstance(response_data, dict) and 'value' in response_data:
                    items = response_data.get('value', [])
                    all_items.extend(items)
                    
                    if config.DEBUG:
                        config.logger.debug(f"Retrieved {len(items)} items from OData API")
                    
                    # Check if there's a nextLink for more pages
                    current_url = response_data.get('@odata.nextLink', None)
                    
                    if current_url and config.DEBUG:
                        config.logger.debug(f"Found @odata.nextLink: {current_url}")
                else:
                    # If response doesn't match expected format, just return it
                    if config.DEBUG:
                        config.logger.warning("Response doesn't contain 'value' array, returning as is")
                    return response_data
            
            # Add a small delay to avoid rate limiting
            if current_url:
                time.sleep(0.2)
        
        if config.DEBUG:
            config.logger.debug(f"Completed paginated request to {endpoint}, retrieved {len(all_items)} total items")
        
        # Ensure we always return data in the format postgres_client expects
        return {'Items': all_items}

    def query_api(self, api_name, **kwargs):
        """
        Funzione generica per eseguire query alle API Citrix basate sulla configurazione.
        
        Args:
            api_name: Nome dell'API da interrogare, deve corrispondere a una chiave in api_configs
            **kwargs: Parametri aggiuntivi per sovrascrivere la configurazione di default
            
        Returns:
            dict: Risposta dell'API
        """
        from database.postgres_client import postgres_manager
        
        if api_name not in self.api_configs:
            config.logger.error(f"API configuration for '{api_name}' not found")
            return None
        
        api_config = self.api_configs[api_name].copy()
        
        # Sovrascrivi i parametri della configurazione con quelli forniti
        for key, value in kwargs.items():
            if key in api_config:
                api_config[key] = value
        
        endpoint = api_config.get("endpoint")
        if not endpoint:
            config.logger.error(f"Endpoint not defined for API '{api_name}'")
            return None
        
        # Get the API type from configuration
        api_type = api_config.get("type")
        
        # Gestione speciale per API di tipo log
        if api_type == "log":
            return self._handle_log_api(api_name, api_config)
        
        # Gestione delle API che richiedono paginazione o sono di tipo REST
        if api_config.get("pagination", False) or api_type == "rest":
            return self.get_with_pagination(endpoint, api_type=api_type)
        
        # Costruisci la query OData
        query_parts = []
        
        # Gestione delle API con filtri temporali
        if "filter_field" in api_config:
            filter_field = api_config["filter_field"]
            
            # Calcola intervallo temporale
            end_time = datetime.now()
            if "time_window" in api_config:
                time_window = int(api_config["time_window"])
                end_time = end_time - timedelta(seconds=time_window)
            
            # Tenta di recuperare l'ultimo timestamp di esecuzione per questo endpoint da PostgreSQL
            last_endpoint_run = postgres_manager.get_last_endpoint_run(api_name)
            
            if last_endpoint_run:
                # Se esiste un'ultima esecuzione, usa quel timestamp come inizio
                config.logger.info(f"Using last execution timestamp for {api_name}: {last_endpoint_run}")
                # Gestisce il formato ISO con o senza la 'Z' finale
                if last_endpoint_run.endswith('Z'):
                    last_endpoint_run = last_endpoint_run[:-1]
                start_time = datetime.fromisoformat(last_endpoint_run)
            else:
                # Se non esiste, usa un'ora indietro come default
                config.logger.info(f"No previous execution found for {api_name}, using default (1 hour ago)")
                start_time = end_time - timedelta(hours=1)
            
            # Formatta le date per OData
            start_time_formatted = start_time.isoformat().split('.')[0] + 'Z'
            end_time_formatted = end_time.isoformat().split('.')[0] + 'Z'
            
            # Aggiungi filtro temporale
            query_parts.append(f"$filter={filter_field} ge {start_time_formatted} and {filter_field} lt {end_time_formatted}")
        
        # Aggiungi campi da selezionare
        if "select" in api_config and api_config["select"]:
            query_parts.append(f"$select={','.join(api_config['select'])}")
        
        # Aggiungi expand con select nidificati
        if "expand" in api_config and api_config["expand"]:
            expand_parts = []
            for key, fields in api_config["expand"].items():
                if fields:
                    expand_parts.append(f"{key}($select={','.join(fields)})")
            
            if expand_parts:
                query_parts.append(f"$expand={','.join(expand_parts)}")
        
        # Aggiungi ordinamento
        if "order_by" in api_config and api_config["order_by"]:
            query_parts.append(f"$orderby={api_config['order_by']}")
        
        # Unisci tutte le parti della query
        query_string = "&".join(query_parts)
        
        if config.DEBUG:
            config.logger.debug(f"{api_name} OData query string: {query_string}")
        
        # Se abbiamo parametri di query, esegui la richiesta con i parametri
        if query_parts:
            # Esegui la query
            response = self._make_request('GET', endpoint, params=query_string, use_query_string=True, api_type=api_type)
            
            # Se c'è un filtro temporale, salva il timestamp di fine come ultima esecuzione
            if "filter_field" in api_config:
                postgres_manager.store_last_endpoint_run(api_name, end_time)
            
            return response
        
        # Caso semplice: solo endpoint senza parametri aggiuntivi
        response = self._make_request('GET', endpoint, api_type=api_type)
        
        # Check for REST API pagination or OData nextLink
        if isinstance(response, dict):
            if api_type == 'rest' and 'ContinuationToken' in response:
                config.logger.debug(f"Detected ContinuationToken in response, handling pagination for {api_name}")
                return self.get_with_pagination(endpoint, api_type='rest')
            elif '@odata.nextLink' in response:
                config.logger.debug(f"Detected @odata.nextLink in response, handling pagination for {api_name}")
                return self.get_with_pagination(endpoint)
            
        return response

    def _handle_log_api(self, api_name, api_config):
        """
        Gestisce le API di tipo 'log', che richiedono una gestione speciale.
        
        Args:
            api_name: Nome dell'API da interrogare
            api_config: Configurazione dell'API
            
        Returns:
            dict: Risposta dell'API
        """
        config.logger.info(f"Handling log API request for {api_name}")
        if config.DEBUG:
            config.logger.debug(f"API config: {json.dumps(api_config)}")
        from database.postgres_client import postgres_manager
        from database.victorialogs_client import victoria_logs_manager
        
        endpoint = api_config.get("endpoint")
        days_to_search = api_config.get("days_to_search", 7)
        
        # Build query parameter for days
        params = {
            "days": days_to_search
        }
        
        # Make REST API request with days parameter
        config.logger.info(f"Querying {api_name} API with endpoint {endpoint} and days={days_to_search}")
        response = self._make_request('GET', endpoint, params=params, api_type='rest')
        
        if not response:
            config.logger.warning(f"Empty response from log API {api_name}")
            return None
            
        if config.DEBUG:
            if isinstance(response, dict):
                config.logger.debug(f"Response type: dict, keys: {list(response.keys())}")
            elif isinstance(response, list):
                config.logger.debug(f"Response type: list, length: {len(response)}")
            else:
                config.logger.debug(f"Response type: {type(response)}")
            
        # Extract items from response
        items = []
        if isinstance(response, dict):
            if 'Items' in response:
                items = response['Items']
                if config.DEBUG:
                    config.logger.debug(f"Found {len(items)} items in 'Items' field (log API format)")
            elif 'value' in response:
                items = response['value']
                if config.DEBUG:
                    config.logger.debug(f"Found {len(items)} items in 'value' field")
        elif isinstance(response, list):
            items = response
            
        if not items:
            config.logger.info(f"No log entries found for {api_name}")
            return response
            
        # Filter logs based on the last execution timestamp
        last_endpoint_run = postgres_manager.get_last_endpoint_run(api_name)
        filtered_items = []
        
        if last_endpoint_run:
            # If we have a last execution, filter logs
            config.logger.info(f"Filtering logs for {api_name} after timestamp: {last_endpoint_run}")
            
            # Handle ISO format with or without 'Z'
            if last_endpoint_run.endswith('Z'):
                last_endpoint_run = last_endpoint_run[:-1]
            
            try:
                last_run_timestamp = datetime.fromisoformat(last_endpoint_run)
                
                # Filter based on FormattedEndTime
                for item in items:
                    if "FormattedEndTime" in item:
                        entry_timestamp = item["FormattedEndTime"]
                        # Handle ISO format with or without 'Z'
                        if entry_timestamp.endswith('Z'):
                            entry_timestamp = entry_timestamp[:-1]
                        
                        try:
                            entry_date = datetime.fromisoformat(entry_timestamp)
                            if entry_date > last_run_timestamp:
                                filtered_items.append(item)
                        except ValueError:
                            # Keep item if timestamp parsing fails
                            filtered_items.append(item)
                    else:
                        # Keep items without timestamp
                        filtered_items.append(item)
            except ValueError:
                # If timestamp parsing fails, use all items
                config.logger.warning(f"Failed to parse last execution timestamp for {api_name}, using all logs")
                filtered_items = items
        else:
            # No last execution, use all items
            config.logger.info(f"No previous execution found for {api_name}, using all logs")
            filtered_items = items
            
        if filtered_items:
            config.logger.info(f"Found {len(filtered_items)} new log entries for {api_name}")
            
            # Try to send logs to VictoriaLogs, but don't block if it fails
            try:
                victoria_logs_manager.write_logs(
                    filtered_items,
                    log_source=f"citrix_{api_name}",
                    metric_type="citrix_logs"
                )
            except Exception as e:
                config.logger.error(f"Failed to send logs to VictoriaLogs: {str(e)}")
                config.logger.info("Continuing with processing despite VictoriaLogs error")
            
            # Update the last execution timestamp using the latest FormattedEndTime
            try:
                latest_timestamp = None
                
                for item in filtered_items:
                    if "FormattedEndTime" in item:
                        entry_timestamp = item["FormattedEndTime"]
                        if latest_timestamp is None or entry_timestamp > latest_timestamp:
                            latest_timestamp = entry_timestamp
                
                if latest_timestamp:
                    postgres_manager.store_last_endpoint_run(api_name, latest_timestamp)
                    config.logger.debug(f"Updated last execution timestamp for {api_name} to {latest_timestamp}")
                else:
                    config.logger.warning(f"No FormattedEndTime found in any log entries for {api_name}")
            except Exception as e:
                config.logger.error(f"Failed to update last execution timestamp: {str(e)}")
        else:
            config.logger.info(f"No new log entries for {api_name}")
        
        # Format response to be compatible with the collect_metrics function
        # This ensures both our VictoriaLogs and standard metric collection paths work
        formatted_response = {'value': filtered_items}
        
        if config.DEBUG:
            config.logger.debug(f"Returning {len(filtered_items)} items for API {api_name}")
            
        # Special handler: if filtered_items is empty, return empty list instead of empty dict
        # This prevents collect_metrics from trying to process an empty response
        if not filtered_items:
            if config.DEBUG:
                config.logger.debug(f"No filtered items for API {api_name}, returning empty list")
            return []
            
        # Return filtered items in a format compatible with collect_metrics
        if isinstance(response, dict) and 'value' in response:
            response['value'] = filtered_items
            return response
        return formatted_response
        
    # Manteniamo i metodi legacy per compatibilità
    def get_metrics(self, metric_type, start_time=None, end_time=None):
        """
        Metodo legacy per compatibilità che ora utilizza query_api.
        
        Args:
            metric_type: Tipo di metriche da recuperare (es. 'sessions', 'machines', ecc.)
            start_time: Tempo di inizio per la query delle metriche (formato ISO)
            end_time: Tempo di fine per la query delle metriche (formato ISO)
            
        Returns:
            Dati delle metriche
        """
        config.logger.warning(f"Using deprecated get_metrics method with {metric_type}, consider using query_api directly")
        
        if metric_type == 'sessions' or metric_type == 'connections':
            # Sostituisci con load_indexes
            response = self.query_api('load_indexes')
            # Trasforma la risposta per corrispondere al formato legacy
            if response and 'value' in response:
                return {'items': response['value']}
            return {'items': []}
        elif metric_type == 'machines':
            # Per le macchine usiamo l'endpoint di configurazione
            machines = self.query_api('machines')
            # Trasforma al formato legacy
            if machines:
                return {'items': machines}
            return {'items': []}
        else:
            config.logger.error(f"Unsupported metric type: {metric_type}")
            return {'items': []}

    def get_site_id(self):
        """
        Retrieve the Citrix Site ID from the Citrix API.
        Makes a GET request to the Citrix API endpoint /cvad/manage/me 
        and extracts the ID from Customers[0].Sites[0].Id in the response.
        Also stores the site_id as an instance variable for use in REST API calls.
        
        Returns:
            str: The Site ID or None if not found
        """
        try:
            config.logger.info("Retrieving Citrix Site ID from API")
            
            # The endpoint is /cvad/manage/me
            endpoint = '/cvad/manage/me'
            
            # Make the request
            response = self._make_request('GET', endpoint)
            
            if response and 'Customers' in response and len(response['Customers']) > 0:
                if 'Sites' in response['Customers'][0] and len(response['Customers'][0]['Sites']) > 0:
                    site_id = response['Customers'][0]['Sites'][0]['Id']
                    config.logger.info(f"Successfully retrieved Citrix Site ID: {site_id}")
                    
                    # Store the site_id as an instance variable
                    self.site_id = site_id
                    
                    return site_id
                else:
                    config.logger.warning("No Sites found in the API response")
            else:
                config.logger.warning("No Customers found in the API response")
                
            return None
            
        except Exception as e:
            config.logger.error(f"Failed to retrieve Citrix Site ID: {str(e)}")
            if config.DEBUG:
                import traceback
                config.logger.debug(f"Detailed error traceback: {traceback.format_exc()}")
            return None

# Create a singleton instance of the API client
citrix_client = CitrixAPIClient()