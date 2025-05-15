import psycopg2
import json
import re
import os
import yaml
from datetime import datetime

from utils import config

class PostgresManager:
    def __init__(self):
        self.host = config.POSTGRES_HOST
        self.port = config.POSTGRES_PORT
        self.dbname = config.POSTGRES_DB
        self.user = config.POSTGRES_USER
        self.password = config.POSTGRES_PASSWORD
        self.conn = None
        self.cursor = None
        
        # Load field type definitions
        self.field_type_definitions = self._load_field_type_definitions()
        
        # Initialize connection and tables
        self.connect()
        self.init_tables()
        
        # Synchronize the database with the API configuration
        try:
            self.synchronize_database_with_api_config()
        except Exception as e:
            config.logger.error(f"Error during initial database synchronization: {str(e)}")
            # We don't want to block the application startup if synchronization fails
    
    def connect(self):
        """Connect to PostgreSQL database."""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password
            )
            self.conn.autocommit = True
            self.cursor = self.conn.cursor()
            config.logger.info(f"Connected to PostgreSQL at {self.host}:{self.port}")
        except Exception as e:
            config.logger.error(f"Failed to connect to PostgreSQL: {str(e)}")
            raise
    
    def init_tables(self):
        """Initialize the database tables if they don't exist."""
        try:
            # Load API configuration using centralized function
            api_configs = config.load_api_config()
            
            if not api_configs:
                config.logger.error("API configuration not found, aborting table initialization")
                return
                
            # Create system tables dynamically based on REST API configurations
            # First create base tables for main entities (without foreign key constraints)
            
            # Keep track of REST API entities found
            rest_api_tables = []
            
            # Iterate through each API configuration
            for entity_name, entity_config in api_configs.items():
                # Only process REST API types
                if entity_config.get('type') == 'rest':
                    config.logger.info(f"Creating table for REST API entity: {entity_name}")
                    
                    # Create table name with citrix_ prefix
                    table_name = f"citrix_{entity_name}"
                    rest_api_tables.append(table_name)
                    
                    # Create the basic table structure with mandatory fields
                    self.cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                        id VARCHAR(255) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        collected_at TIMESTAMP NOT NULL
                    )
                    """)
            
            # No relationship tables will be created as per requirements
            
            # Create table for auth tokens
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS citrix_auth_tokens (
                id SERIAL PRIMARY KEY,
                token TEXT NOT NULL,
                expiry_time TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """)
            
            # Create table for endpoint last run timestamps
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS endpoint_last_run (
                endpoint VARCHAR(255) PRIMARY KEY,
                last_run_timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """)
            
            # Create table for Citrix site ID
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS citrix_site_id (
                id SERIAL PRIMARY KEY,
                site_id VARCHAR(255) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """)
            
            # Now dynamically add columns to tables based on API configuration 'select' fields
            for entity_name, entity_config in api_configs.items():                    # Only process REST API types
                if entity_config.get('type') == 'rest':
                    table_name = f"citrix_{entity_name}"
                    
                    # Process 'select' fields
                    if 'select' in entity_config and isinstance(entity_config['select'], list):
                        for field in entity_config['select']:
                            # Skip id and name as they're already part of the base table structure
                            if field.lower() in ['id', 'name']:
                                continue
                                
                            # Convert field name to lowercase for column name, preserving original structure
                            column_name = self._to_lowercase(field)
                            
                            # Check if this is a multi-value field
                            is_multi_value = ('multi_value_fields' in entity_config and 
                                            field in entity_config['multi_value_fields'])
                            
                            # Determine appropriate SQL data type based on field name and multi-value status
                            base_type = self._infer_field_type_from_name(field)
                            sql_type = f"{base_type}[]" if is_multi_value else base_type
                            
                            # Add column if it doesn't exist
                            try:
                                self.cursor.execute(f"""
                                ALTER TABLE {table_name}
                                ADD COLUMN IF NOT EXISTS {column_name} {sql_type}
                                """)
                            except Exception as col_err:
                                config.logger.warning(f"Error adding column {column_name} to {table_name}: {str(col_err)}")
                    
                    # Process 'expand' fields if they exist
                    if 'expand' in entity_config:
                        expand_config = entity_config['expand']
                        
                        # Handle different expand formats
                        if isinstance(expand_config, dict):
                            # Format: expand: { Entity: ["Field1", "Field2"] }
                            for expand_entity, expand_fields in expand_config.items():
                                # No foreign key columns will be added as per requirements
                                        
                                # Add columns for expanded fields
                                if isinstance(expand_fields, list):
                                    for field in expand_fields:
                                        # Skip id as it's handled separately
                                        # if field.lower() == 'id':
                                        #     continue
                                            
                                        # Create column name with entity prefix and underscore to avoid conflicts
                                        # Format: EntityName_FieldName (e.g., DeliveryGroup_Id -> delivery_group_id)
                                        column_name = f"{expand_entity.lower()}{field.lower()}"
                                        
                                        # Determine SQL data type
                                        sql_type = self._infer_field_type_from_name(field)
                                        
                                        # Add column if it doesn't exist
                                        try:
                                            self.cursor.execute(f"""
                                            ALTER TABLE {table_name}
                                            ADD COLUMN IF NOT EXISTS {column_name} {sql_type}
                                            """)
                                        except Exception as exp_field_err:
                                            config.logger.warning(f"Error adding expanded field column {column_name} to {table_name}: {str(exp_field_err)}")
                        
                        # elif isinstance(expand_config, list):
                        #     # Format: expand: ["Field1", "Field2"]
                        #     for field in expand_config:
                        #         # Store multi-value fields as normal fields
                        #         # No relationships between tables will be created
                        #         pass  # Placeholder for future implementation
            
            config.logger.info("Database tables initialized dynamically based on API configuration")
            
        except Exception as e:
            config.logger.error(f"Failed to initialize database tables: {str(e)}")
            raise
    
    # def update_table_schemas(self):
    #     """
    #     Dynamically updates table schemas to align them with the API configuration.
    #     This function automatically detects differences between the database schema
    #     and the API configuration, making only the necessary changes.
    #     """
    #     try:
    #         # Load the API configuration using centralized function
    #         api_configs = config.load_api_config()
            
    #         if not api_configs:
    #             config.logger.error("API configuration not found, aborting table schema update")
    #             return
            
    #         # Map API entities to database tables
    #         entity_to_table = self._get_entity_table_mapping()
            
    #         # For each table, verify and update the schema
    #         for entity_name, table_name in entity_to_table.items():
    #             if entity_name in api_configs:
    #                 config.logger.info(f"Updating table schema {table_name} based on API configuration")
                    
    #                 # Get fields from API configuration
    #                 api_fields = self._extract_entity_fields(entity_name, api_configs[entity_name])
                    
    #                 # Get fields currently in the table
    #                 self.cursor.execute(f"""
    #                 SELECT column_name 
    #                 FROM information_schema.columns 
    #                 WHERE table_name = '{table_name}'
    #                 """)
                    
    #                 existing_columns = [row[0] for row in self.cursor.fetchall()]
                    
    #                 # Convert API field names to lowercase to compare them with DB field names
    #                 api_fields_lower = [self._to_lowercase(field) for field in api_fields]
                    
    #                 # System fields that should not be removed
    #                 system_fields = ['id', 'name', 'collected_at']
                    
    #                 # Find obsolete fields that need to be removed
    #                 # (those in the DB but not in the API configuration and not system fields)
    #                 obsolete_columns = [col for col in existing_columns 
    #                                    if col not in api_fields_lower
    #                                    and col not in system_fields]
                    
    #                 # Remove obsolete columns
    #                 if obsolete_columns:
    #                     config.logger.info(f"Removing obsolete columns from {table_name}: {', '.join(obsolete_columns)}")
                        
    #                     for col in obsolete_columns:
    #                         try:
    #                             self.cursor.execute(f"""
    #                             ALTER TABLE {table_name}
    #                             DROP COLUMN IF EXISTS {col}
    #                             """)
    #                             config.logger.info(f"Removed column {col} from table {table_name}")
    #                         except Exception as col_err:
    #                             config.logger.warning(f"Unable to remove column {col} from {table_name}: {str(col_err)}")
                    
    #                 # We no longer need column renames as we're using direct lowercase mapping
            
    #         config.logger.info("Database schema dynamically updated based on API configuration")
    #     except Exception as e:
    #         config.logger.error(f"Error updating database schema: {str(e)}")
    #         raise
    
    def generate_schema_from_api_config(self):
        """
        Dynamically generates the database schema based on API configurations.
        This function reads the api_config.yaml file for each configuration entity,
        creates or updates the corresponding tables with the appropriate fields.
        """
        try:
            # Retrieve the API configuration using the centralized function
            api_configs = config.load_api_config()
            
            if not api_configs:
                config.logger.error("API configuration not found, aborting schema generation")
                return
            
            config.logger.info("API configuration loaded successfully")
            
            # Map configuration entities to DB tables
            config_to_table = self._get_entity_table_mapping()
            
            # For each configuration entity
            for config_name, table_name in config_to_table.items():
                if config_name in api_configs:
                    self._update_table_schema(config_name, table_name, api_configs[config_name])
            
            config.logger.info("Database schema dynamically generated from API configurations")
        except Exception as e:
            config.logger.error(f"Error generating schema from API configuration file: {str(e)}")
            raise
    
    def generate_field_types_from_api_config(self):
        """
        Analyzes the API configuration and generates field type definitions based on field names
        and naming conventions. This can be used to bootstrap the field_types.yaml file.
        
        Returns:
            dict: Generated field type definitions
        """
        try:
            # Load API configuration using centralized function
            api_configs = config.load_api_config()
            
            if not api_configs:
                error_msg = "API configuration not found, cannot generate field types"
                config.logger.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            # Initialize field type definitions with common fields
            field_types = {
                'common_fields': {
                    'Id': 'VARCHAR(255)',
                    'Name': 'VARCHAR(255)',
                    'collected_at': 'TIMESTAMP'
                }
            }
            
            # Initialize entity-specific field types
            for entity in ['delivery_groups', 'machines', 'catalogs', 'applications']:
                field_types[entity] = {}
            
            # Define naming conventions for type determination
            field_types['default_types'] = {
                'prefixes': {
                    'is_': 'BOOLEAN',
                    'has_': 'BOOLEAN',
                    'count_': 'INTEGER'
                },
                'suffixes': {
                    '_id': 'VARCHAR(255)',
                    '_count': 'INTEGER',
                    '_date': 'TIMESTAMP',
                    '_time': 'TIMESTAMP',
                    '_type': 'INTEGER',
                    '_state': 'INTEGER',
                    '_mode': 'INTEGER',
                    '_status': 'INTEGER'
                },
                'default': 'VARCHAR(255)'
            }
            
            # Process each entity in the API configuration
            for entity, config_data in api_configs.items():
                if entity not in field_types:
                    continue
                    
                # Extract fields from 'select' section
                if 'select' in config_data and isinstance(config_data['select'], list):
                    fields = config_data['select']
                    
                    for field in fields:
                        # Skip common fields that are already defined
                        if field in field_types['common_fields']:
                            continue
                            
                        # Determine field type based on name and entity type
                        # Using _determine_field_type to ensure consistent type inference across the application
                        field_type = self._determine_field_type(field, entity)
                        
                        # Add to entity-specific field types
                        field_types[entity][field] = field_type
            
            return field_types
        except Exception as e:
            config.logger.error(f"Error generating field types from API config: {str(e)}")
            raise
    
    def _infer_field_type_from_name(self, field_name):
        """
        Get field type from configuration files.
        If the field contains 'Id', returns VARCHAR(255).
        Otherwise returns VARCHAR(255) as default.
        
        Args:
            field_name (str): Field name to analyze
            
        Returns:
            str: SQL data type string
        """
        # Handle Id fields
        if 'Id' in field_name:
            return 'VARCHAR(255)'
            
        # Default to VARCHAR if not found in configuration
        return 'VARCHAR(255)'
    
    def synchronize_database_with_api_config(self):
        """
        Synchronizes the database structure with the API configuration.
        This method performs maintenance operations such as:
        1. Updating table schemas
        2. Cleaning up obsolete data
        3. Managing renamed fields
        """
        try:
            config.logger.info("Synchronizing database with API configuration...")
                        # Display field type mappings for diagnosis if in debug mode
            if config.DEBUG:
                self.display_field_type_mappings()
            # Update table schemas
            #self.update_table_schemas()
            
            # Dynamically generate tables from API configuration
            self.generate_schema_from_api_config()
            
            # Get the complete list of fields from API configuration
            api_configs = config.load_api_config()
            
            if not api_configs:
                config.logger.error("API configuration not found, cannot synchronize database fields")
                return
            
            # Map API entities to database tables
            entity_to_table = self._get_entity_table_mapping()
            
            # For each entity, verify that the table fields match those in the API config
            for entity, table_name in entity_to_table.items():
                if entity in api_configs:
                    self._synchronize_table_fields(table_name, api_configs[entity])
            
            config.logger.info("Database synchronization completed successfully")
        except Exception as e:
            config.logger.error(f"Error synchronizing database: {str(e)}")
            raise
            
    def _get_entity_table_mapping(self):
        """Get the mapping from API entity names to database table names."""
        return {
            'delivery_groups': 'citrix_delivery_groups',
            'machines': 'citrix_machines',
            'catalogs': 'citrix_catalogs',
            'applications': 'citrix_applications'
        }
        
    def _extract_entity_fields(self, entity_name, api_config):
        """
        Extract fields from the API configuration for a specific entity.
        
        Args:
            entity_name: Entity name (e.g., 'delivery_groups')
            api_config: API configuration for the entity
            
        Returns:
            list: List of fields defined in the API configuration
        """
        fields = []
        
        # Extract fields from 'select' section
        if 'select' in api_config and isinstance(api_config['select'], list):
            fields.extend(api_config['select'])
            
        # Add system fields that are always needed
        system_fields = ['Id', 'Name', 'collected_at']
        for field in system_fields:
            if field not in fields:
                fields.append(field)
                
        return fields
    
    def _synchronize_table_fields(self, table_name, api_config):
        """
        Synchronize table fields with those defined in the API configuration.
        
        Args:
            table_name: Table name
            api_config: API configuration for the corresponding entity
        """
        try:
            # Get the list of fields from the API configuration
            fields = self._extract_entity_fields(table_name, api_config)
                
            # Get the list of fields currently in the table
            self.cursor.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
            """)
            
            existing_columns = [row[0] for row in self.cursor.fetchall()]
            
            # Convert API field names to lowercase
            api_fields_lowercase = [self._to_lowercase(field) for field in fields]
            
            # Look for obsolete fields (those that exist in the table but not in the API configuration)
            # Ignore system fields like id, name, collected_at
            system_fields = ['id', 'name', 'collected_at', 'delivery_group_id', 'catalog_id']
            obsolete_fields = [col for col in existing_columns 
                              if col not in api_fields_lowercase
                              and col not in system_fields]
            
            if obsolete_fields:
                config.logger.info(f"Obsolete fields found in {table_name}: {obsolete_fields}")
                
                # Consider whether to automatically remove obsolete fields
                # For safety, we keep them but log a warning
                for field in obsolete_fields:
                    config.logger.warning(f"Obsolete field '{field}' found in {table_name}. "
                                        f"It is not present in the API configuration but will not be automatically removed.")
            
            # No special field renaming - we're keeping original fields (just lowercase)
            config.logger.info(f"Using simple lowercase field names for table {table_name}")
                            
            config.logger.info(f"Field synchronization completed for table {table_name}")
        except Exception as e:
            config.logger.error(f"Error synchronizing fields for table {table_name}: {str(e)}")
            raise
    
    def _update_table_schema(self, config_name, table_name, api_config):
        """
        Updates a table schema based on the API configuration.
        Preserves original CamelCase field names.
        
        Args:
            config_name: Name of the configuration entity (e.g., delivery_groups)
            table_name: Database table name (e.g., citrix_delivery_groups)
            api_config: API configuration for the entity
        """
        try:
            # Get fields from the API configuration
            fields = self._extract_entity_fields(config_name, api_config)
            
            # Map field names to SQL definitions using dynamic type determination
            field_definitions = []
            for field in fields:
                # Keep original CamelCase field names
                db_field = field
                
                # Handle special cases for primary keys and required fields
                if field == 'Id':
                    field_definitions.append('id VARCHAR(255) PRIMARY KEY')
                elif field == 'Name':
                    field_definitions.append('name VARCHAR(255) NOT NULL')
                elif field == 'collected_at':
                    field_definitions.append('collected_at TIMESTAMP NOT NULL')
                else:
                    # Determine field type dynamically
                    field_type = self._determine_field_type(field, config_name)
                    # Convert to lowercase for table creation
                    db_field = field.lower()
                    field_definitions.append(f'{db_field} {field_type}')
            
            # Create or modify the table
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {', '.join(field_definitions)}
            )
            """
            
            self.cursor.execute(create_table_query)
            config.logger.info(f"Created/updated table {table_name} for configuration {config_name}")                # Check and add missing columns
            for field_def in field_definitions:
                field_parts = field_def.split(' ', 1)  # Split only on the first space
                field_name = field_parts[0]  # Field name without quotes
                field_type = field_parts[1] if len(field_parts) > 1 else 'VARCHAR(255)'
                
                # Skip the special fields that are always present
                if field_name in ['id', 'name', 'collected_at']:
                    continue
                
                try:
                    # Add column if it doesn't exist
                    # Don't use quotes for column names in Postgres table creation
                    add_column_query = f"""
                    ALTER TABLE {table_name}
                    ADD COLUMN IF NOT EXISTS {field_name} {field_type}
                    """
                    self.cursor.execute(add_column_query)
                except Exception as e:
                    config.logger.warning(f"Unable to add column {field_name} to table {table_name}: {str(e)}")
            
            config.logger.info(f"Table schema for {table_name} updated based on API configuration")
        except Exception as e:
            config.logger.error(f"Error updating table schema for {table_name}: {str(e)}")
            raise
    
    def _to_lowercase(self, name):
        """
        Convert a string to lowercase preserving the original structure.
        No snake_case conversion, just lowercase.
        
        Args:
            name (str): String to convert (usually a field name)
            
        Returns:
            str: Converted lowercase string
        """
        if not name:
            return name
            
        return name.lower()
        
    def _load_field_type_definitions(self):
        """
        Load field type definitions from YAML configuration.
        
        Returns:
            dict: Field type definitions loaded from configuration or default values
        """
        try:
            # Try to load from file first
            field_types_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config', 'field_types.yaml')
            
            if os.path.exists(field_types_file):
                with open(field_types_file, 'r') as f:
                    field_types = yaml.safe_load(f)
                    config.logger.info("Field type definitions loaded from configuration file")
                    return field_types
            else:
                config.logger.warning("Field types configuration file not found, using default type inference")
        except Exception as e:
            config.logger.warning(f"Error loading field type definitions: {str(e)}, using default type inference")
        
        # Return minimal default configuration if file loading fails
        return {
            'common_fields': {
                'Id': 'VARCHAR(255)',
                'Name': 'VARCHAR(255)',
                'collected_at': 'TIMESTAMP'
            }
        }
    
    def _determine_field_type(self, field_name, entity=None):
        """
        Determines the appropriate SQL data type for a field based on name conventions and configurations.
        
        Args:
            field_name (str): The name of the field
            entity (str, optional): The entity this field belongs to
            
        Returns:
            str: SQL data type string
        """
        # First check if we have entity-specific type definitions
        if entity and entity in self.field_type_definitions:
            entity_types = self.field_type_definitions[entity]
            if field_name in entity_types:
                return entity_types[field_name]
        
        # If not found in entity-specific types, infer from name
        return self._infer_field_type_from_name(field_name)
    
    def _normalize_field_name(self, field_name):
        """
        Normalizes a field name for SQL use - converting to lowercase and handling special characters.
        
        Args:
            field_name (str): The original field name
            
        Returns:
            str: The normalized field name safe for SQL use
        """
        # Convert to lowercase for SQL consistency
        normalized = field_name.lower()
        
        # Common SQL keywords that might need special handling
        sql_keywords = ['order', 'group', 'where', 'from', 'select', 'update', 'delete', 'insert', 'values', 'type']
        
        # If the field is a SQL keyword, we would normally handle it specially
        # but since we're consistently using all lowercase table columns without quotes,
        # we'll just return the lowercase version
        return normalized
    
    def store_auth_token(self, token, expiry_time):
        """
        Salva il bearer token nel database.
        
        Args:
            token: Il bearer token
            expiry_time: Data e ora di scadenza del token
        """
        try:
            # Prima elimina tutti i token precedenti
            self.cursor.execute("DELETE FROM citrix_auth_tokens")
            
            # Poi inserisci il nuovo token
            self.cursor.execute("""
            INSERT INTO citrix_auth_tokens (token, expiry_time)
            VALUES (%s, %s)
            """, (
                token,
                expiry_time
            ))
            
            config.logger.info(f"Bearer token salvato nel database, scadenza: {expiry_time}")
        except Exception as e:
            config.logger.error(f"Errore nel salvataggio del token nel database: {str(e)}")
            # Non lanciare l'eccezione per evitare blocchi nell'autenticazione
    
    def get_auth_token(self):
        """
        Recupera il token più recente dal database se non è scaduto.
        
        Returns:
            Tuple (token, expiry_time) o (None, None) se non trovato o scaduto
        """
        try:
            self.cursor.execute("""
            SELECT token, expiry_time FROM citrix_auth_tokens
            WHERE expiry_time > NOW()
            ORDER BY created_at DESC
            LIMIT 1
            """)
            
            result = self.cursor.fetchone()
            if result:
                token, expiry = result
                config.logger.info(f"Token recuperato dal database, scadenza: {expiry}")
                return token, expiry
            
            config.logger.debug("Nessun token valido trovato nel database")
            return None, None
        except Exception as e:
            config.logger.error(f"Errore nel recupero del token dal database: {str(e)}")
            return None, None
    
    def store_last_endpoint_run(self, endpoint, timestamp):
        """
        Memorizza il timestamp dell'ultima esecuzione di una specifica query endpoint.
        
        Args:
            endpoint: Nome dell'endpoint API
            timestamp: Timestamp in formato ISO da memorizzare
        """
        try:
            # Se il timestamp è una stringa ISO, convertilo in oggetto datetime
            if isinstance(timestamp, str):
                # Gestisce il formato ISO con o senza la 'Z' finale
                if timestamp.endswith('Z'):
                    timestamp = timestamp[:-1]
                # Gestisce il formato ISO con millisecondi
                if '.' in timestamp:
                    dt_timestamp = datetime.fromisoformat(timestamp)
                else:
                    dt_timestamp = datetime.fromisoformat(timestamp)
            else:
                dt_timestamp = timestamp
            
            self.cursor.execute("""
            INSERT INTO endpoint_last_run (endpoint, last_run_timestamp, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (endpoint) DO UPDATE SET
                last_run_timestamp = EXCLUDED.last_run_timestamp,
                updated_at = NOW()
            """, (
                endpoint,
                dt_timestamp
            ))
            
            config.logger.debug(f"Stored last run timestamp for endpoint {endpoint}: {timestamp}")
        except Exception as e:
            config.logger.error(f"Error storing last run timestamp for endpoint {endpoint}: {str(e)}")
    
    def get_last_endpoint_run(self, endpoint):
        """
        Recupera il timestamp dell'ultima esecuzione di una specifica query endpoint.
        
        Args:
            endpoint: Nome dell'endpoint API
            
        Returns:
            str: Timestamp in formato ISO dell'ultima esecuzione, o None se non esiste
        """
        try:
            self.cursor.execute("""
            SELECT last_run_timestamp FROM endpoint_last_run
            WHERE endpoint = %s
            """, (endpoint,))
            
            result = self.cursor.fetchone()
            if result:
                timestamp = result[0].isoformat()
                config.logger.debug(f"Retrieved last run timestamp for endpoint {endpoint}: {timestamp}")
                return timestamp
            
            config.logger.debug(f"No last run found for endpoint {endpoint}")
            return None
        except Exception as e:
            config.logger.error(f"Error retrieving last run for endpoint {endpoint}: {str(e)}")
            return None
    
    def store_site_id(self, site_id):
        """Store Citrix site ID in the database and cache."""
        try:
            now = datetime.now()
            # Controlliamo se esiste già un site ID
            self.cursor.execute("SELECT site_id FROM citrix_site_id LIMIT 1")
            result = self.cursor.fetchone()
            
            if result:
                # Aggiorna il record esistente
                self.cursor.execute("""
                UPDATE citrix_site_id
                SET site_id = %s, updated_at = %s
                WHERE id = 1
                """, (site_id, now))
                config.logger.info(f"Updated Citrix site ID in database: {site_id}")
            else:
                # Inserisce un nuovo record
                self.cursor.execute("""
                INSERT INTO citrix_site_id (site_id, created_at, updated_at)
                VALUES (%s, %s, %s)
                """, (site_id, now, now))
                config.logger.info(f"Stored Citrix site ID in database: {site_id}")
            
            # Update the cache
            self._cached_site_id = site_id
            
            return True
        except Exception as e:
            config.logger.error(f"Failed to store Citrix site ID: {str(e)}")
            return False
    
    def get_site_id(self):
        """Retrieve Citrix site ID from cache or database."""
        try:
            # First check if we have it cached
            if hasattr(self, '_cached_site_id') and self._cached_site_id is not None:
                config.logger.debug(f"Using cached Citrix site ID: {self._cached_site_id}")
                return self._cached_site_id

            # If not cached, get from database
            if self.conn is None or self.conn.closed:
                self.connect()
                
            self.cursor.execute("SELECT site_id FROM citrix_site_id LIMIT 1")
            result = self.cursor.fetchone()
            
            if result:
                self._cached_site_id = result[0]  # Cache the site ID
                config.logger.debug(f"Retrieved and cached Citrix site ID from database: {self._cached_site_id}")
                return self._cached_site_id
            else:
                config.logger.debug("No Citrix site ID found in database")
                return None
        except Exception as e:
            config.logger.error(f"Failed to retrieve Citrix site ID: {str(e)}")
            return None
    
    def set_site_id(self, site_id):
        """
        Sets the Citrix site ID in the database.
        This is a convenience wrapper around store_site_id.
        
        Args:
            site_id (str): The Citrix site ID to store
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not site_id:
            config.logger.warning("Attempted to set empty site ID, ignoring")
            return False
            
        try:
            return self.store_site_id(site_id)
        except Exception as e:
            config.logger.error(f"Failed to set Citrix site ID: {str(e)}")
            if config.DEBUG:
                import traceback
                config.logger.debug(f"Detailed error traceback: {traceback.format_exc()}")
            return False
    
    def store_entity(self, entity_type, data, api_callback=None):
        """
        Generic method to store any entity type in the database based on configuration.
        Preserves original CamelCase field names. Handles pagination via continuationToken.
        
        Args:
            entity_type (str): Type of entity (e.g., 'delivery_groups', 'machines', etc.)
            data: The data to store (can be dict, list, or string)
            api_callback: Optional callback function to fetch more pages if continuationToken is present.
                        Function should accept a token parameter and return the next page of data.
        """
        try:
            now = datetime.now()
            table_name = f"citrix_{entity_type}"
            all_items = []

            # Handle OData and REST API response formats
            if isinstance(data, dict):
                # Check for pagination token at root level
                continuation_token = data.get('continuationToken')
                
                # Get API configuration for this entity type
                api_configs = config.load_api_config()
                if not api_configs or entity_type not in api_configs:
                    config.logger.error(f"No API configuration found for {entity_type}")
                    return
                
                entity_config = api_configs[entity_type]
                select_fields = entity_config.get('select', [])
                expand_config = entity_config.get('expand', {})

                # Function to filter item fields based on configuration
                def filter_item_fields(item):
                    filtered_item = {}
                
                    
                    # Add selected fields
                    for field in select_fields:
                        if field in item:
                            filtered_item[field] = item[field]
                            config.logger.debug(f"Added field {field} to filtered item")
                    
                    # Handle expanded fields
                    if expand_config:
                        if isinstance(expand_config, dict):
                            # Handle dictionary format (e.g., DeliveryGroup: ['Id'])
                            for parent_field, child_fields in expand_config.items():
                                if parent_field in item and isinstance(item[parent_field], dict):
                                    for child_field in child_fields:
                                        if child_field in item[parent_field]:
                                            field_name = f"{parent_field}{child_field}"
                                            filtered_item[field_name] = item[parent_field][child_field]
                        elif isinstance(expand_config, list):
                            # Handle list format (e.g., ['AssociatedDeliveryGroupUuids'])
                            for field in expand_config:
                                if field in item:
                                    filtered_item[field] = item[field]
                    
                    return filtered_item

                # Collect all items from REST API or OData response
                raw_items = []
                
                # Extract items from REST API response format
                if 'Items' in data:
                    items = data['Items']
                    config.logger.debug(f"Extracted {len(items)} {entity_type} from 'Items' field")
                    config.logger.debug(f"API Configuration for {entity_type}: {json.dumps(entity_config, indent=2)}")
                    raw_items.extend(items)

                    # Handle pagination if callback is provided
                    while continuation_token and api_callback:
                        config.logger.info(f"Found continuation token for {entity_type}, fetching next page...")
                        try:
                            next_page = api_callback(continuation_token)
                            if isinstance(next_page, dict):
                                continuation_token = next_page.get('continuationToken')
                                if 'Items' in next_page:
                                    items = next_page['Items']
                                    config.logger.debug(f"Extracted additional {len(items)} {entity_type} from paginated response")
                                    raw_items.extend(items)
                            else:
                                config.logger.error(f"Invalid response format from API callback for {entity_type}")
                                break
                        except Exception as e:
                            config.logger.error(f"Error fetching next page for {entity_type}: {str(e)}")
                            break
                    
                # Handle OData response format
                elif 'value' in data:
                    raw_items = data['value']
                    config.logger.debug(f"Extracted {len(raw_items)} {entity_type} from 'value' field")

                # Filter all collected items according to API configuration
                config.logger.debug(f"About to filter {len(raw_items)} items using filter_item_fields")
                all_items = [filter_item_fields(item) for item in raw_items]
                data = all_items
                config.logger.debug(f"After filtering, got {len(all_items)} items")
            
            # Handle string input
            if isinstance(data, str):
                try:
                    data_dict = json.loads(data)
                    if isinstance(data_dict, dict) and 'value' in data_dict:
                        data = data_dict['value']
                    else:
                        data = data_dict
                except json.JSONDecodeError:
                    data = [{"Id": data, "Name": data}]
            
            # Handle None case
            if data is None:
                config.logger.warning(f"Received None for {entity_type} data")
                return
            
            # Ensure data is a list
            if not isinstance(data, list):
                data = [data]
            
            # Track metrics
            stored_count = 0
            skipped_count = 0
            current_ids = []
            
            for item in data:
                if item is None:
                    config.logger.warning(f"Skipping None {entity_type} in list")
                    skipped_count += 1
                    continue
                
                # Process fields using simple lowercase conversion like in table initialization, preserving original structure
                values = {}
                for field, value in item.items():
                    if isinstance(value, dict):
                        # Handle nested objects (from expand configuration)
                        for nested_field, nested_value in value.items():
                            # Combine parent and nested field names with underscore
                            # e.g., DeliveryGroup.Id becomes delivery_group_id
                            field_name = f"{field.lower()}_{nested_field.lower()}"
                            values[field_name] = nested_value
                    else:
                        # Handle flat fields using only lowercase, preserving original structure
                        lowercase_name = self._to_lowercase(field)
                        values[lowercase_name] = value

                # Skip if required fields are missing
                name_field = next((f for f in values.keys() if f == 'name'), None)
                id_field = next((f for f in values.keys() if f == 'id'), None)

                if not name_field or values[name_field] is None:
                    item_id = values.get(id_field, 'unknown') if id_field else 'unknown'
                    config.logger.warning(f"Skipping {entity_type} with ID {item_id} because Name attribute is missing or null")
                    skipped_count += 1
                    continue
                
                # Add ID if missing
                if not id_field:
                    values['Id'] = str(hash(json.dumps(item)))
                
                # Add timestamps
                values['collected_at'] = now
                
                # Track current IDs - make sure to use the id field we found earlier
                current_ids.append(values[id_field] if id_field else values['Id'])
                
                # Generate SQL for insert/update
                fields = list(values.keys())
                # Create a mapping from original field names to their normalized versions
                field_mapping = {field: self._normalize_field_name(field) for field in fields}
                fields_lower = list(field_mapping.values())
                placeholders = ', '.join(['%s'] * len(fields))
                # Use lowercase field names in SQL without quotes
                update_set = ', '.join([f"{field_mapping[field]} = EXCLUDED.{field_mapping[field]}" for field in fields])
                
                query = f"""
                INSERT INTO {table_name} ({', '.join(fields_lower)})
                VALUES ({placeholders})
                ON CONFLICT (id) DO UPDATE SET {update_set}
                """
                
                self.cursor.execute(query, list(values.values()))
                stored_count += 1                # Clean up old records
            if current_ids:
                placeholders = ','.join(['%s'] * len(current_ids))
                self.cursor.execute(f"""
                DELETE FROM {table_name} 
                WHERE id NOT IN ({placeholders})
                """, current_ids)
                deleted_count = self.cursor.rowcount
                if deleted_count > 0:
                    config.logger.info(f"Deleted {deleted_count} {entity_type} that are no longer present")
            
            config.logger.info(f"Stored {stored_count} {entity_type} in PostgreSQL (skipped {skipped_count} records without Name)")
            
        except Exception as e:
            config.logger.error(f"Failed to store {entity_type} in PostgreSQL: {str(e)}")
            raise
    
    def close(self):
        """Close the database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            config.logger.info("PostgreSQL connection closed")

    def _extract_entity_fields(self, entity_name, api_config):
        """
        Extract fields for an entity from the API configuration.
        Centralized helper to avoid code duplication across schema management functions.
        
        Args:
            entity_name (str): Name of the entity in the API config
            api_config (dict): API configuration for the entity
            
        Returns:
            list: List of field names extracted from the API configuration
        """
        # Initialize the fields list
        fields = []
        
        # Extract fields from 'select' section if present
        if 'select' in api_config and isinstance(api_config['select'], list):
            fields.extend(api_config['select'])
        
        # Add Id and Name if not present (these are required fields)
        if 'Id' not in fields:
            fields.append('Id')
        if 'Name' not in fields:
            fields.append('Name')
        
        # Handle expansion fields
        if 'expand' in api_config:
            expand_config = api_config['expand']
            additional_fields = self._process_expanded_fields(expand_config)
            fields.extend(additional_fields)
        
        # Common fields for all tables
        fields.append('collected_at')
        
        # Ignore specific expanded fields that we don't want in the main DB
        ignore_fields = ['AssociatedDeliveryGroupUuids']
        fields = [f for f in fields if f not in ignore_fields]
        
        return fields
    
    def _process_expanded_fields(self, expand_config):
        """
        Centralizes the processing of expanded fields from API configurations.
        This helper function handles different formats of the 'expand' configuration
        and returns a consistent list of additional fields needed.
        
        Args:
            expand_config: The 'expand' section from an API configuration,
                          can be dict or list format
        
        Returns:
            list: Additional fields to be added to the entity fields list
        """
        additional_fields = []
        
        if not expand_config:
            return additional_fields
            
        # Handle dictionary format
        if isinstance(expand_config, dict):
            for expand_key, expand_fields in expand_config.items():
                # No foreign key fields will be added as per requirements
                # Each table will be independent with no relationships
                pass
                    
        # Handle list format
        elif isinstance(expand_config, list):
            for expand_item in expand_config:
                # Special case for delivery group UUIDs
                if expand_item == 'AssociatedDeliveryGroupUuids':
                    # No separate tables will be created for associations
                    # We'll store these as comma-separated values directly in the parent table
                    additional_fields.append(expand_item)
                # Add other expanded fields if needed
                
        return additional_fields
    
    def _get_entity_table_mapping(self):
        """
        Get the mapping from API entity names to database table names.
        Centralizes the entity-to-table mapping to avoid duplicating it across methods.
        
        Returns:
            dict: Mapping from entity names to table names
        """
        return {
            'delivery_groups': 'citrix_delivery_groups',
            'machines': 'citrix_machines',
            'catalogs': 'citrix_catalogs',
            'applications': 'citrix_applications'
        }

    def display_field_type_mappings(self):
        """
        Display current field type mappings for debugging purposes
        """
        try:
            config.logger.debug("Current field type mappings:")
            
            # List all tables
            self.cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name LIKE 'citrix_%'
            """)
            tables = self.cursor.fetchall()
            
            for table in tables:
                table_name = table[0]
                config.logger.debug(f"\nTable: {table_name}")
                
                # Get column information for each table
                self.cursor.execute("""
                    SELECT column_name, data_type, character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))
                
                columns = self.cursor.fetchall()
                for column in columns:
                    col_name, data_type, max_length = column
                    type_info = f"{data_type}"
                    if max_length:
                        type_info += f"({max_length})"
                    config.logger.debug(f"  {col_name}: {type_info}")
                    
        except Exception as e:
            config.logger.error(f"Error displaying field type mappings: {str(e)}")

# Create a singleton instance
postgres_manager = PostgresManager()