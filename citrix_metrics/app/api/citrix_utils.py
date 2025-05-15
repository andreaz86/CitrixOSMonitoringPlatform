"""
Utility functions for API-related tasks in the Citrix Metrics application.
This module contains functions that are shared across API components.

These utility functions address Issue #4: Expanded Fields Handling by centralizing
the logic for processing expanded fields in API configurations and responses.
This reduces redundancy and ensures consistent handling across the application.

Functions:
- process_expand_config_for_query: Generate query parameters for expanded fields
- process_expanded_fields_in_response: Process expanded fields in API responses
"""

import logging
from typing import Dict, List, Union, Any, Optional

def process_expand_config_for_query(expand_config: Union[Dict, List], api_type: str = "odata") -> Dict[str, str]:
    """
    Process expanded fields configuration for API queries.
    Returns parameters to be added to API requests.
    
    Args:
        expand_config (dict or list): Expansion configuration from the API config
        api_type (str): API type, either "odata" or "rest"
        
    Returns:
        dict: Query parameters to be added to the API request
    """
    params = {}
    
    if not expand_config:
        return params
        
    # Handle REST API expansion - non necessario inviare nella chiamata API
    if api_type == "rest":
        # Per le API REST, non aggiungiamo parametri di expand
        # poiché non hanno effetto e i campi espansi vengono gestiti durante l'elaborazione della risposta
        logging.debug("Skipping expand parameters for REST API - will be processed in response")
        return params
    
    # Handle OData API expansion
    elif api_type == "odata":
        expand_parts = []
        if isinstance(expand_config, dict):
            for key, fields in expand_config.items():
                if fields:
                    expand_parts.append(f"{key}($select={','.join(fields)})")
            
            if expand_parts:
                params["$expand"] = ",".join(expand_parts)
                logging.debug(f"Adding expand parameters to OData API: {params['$expand']}")
    
    return params

def process_expanded_fields_in_response(items: List[Dict], response: Dict, expand_config: Union[Dict, List]) -> List[Dict]:
    """
    Process expanded fields in API response data.
    
    Args:
        items (list): List of items from the response
        response (dict): Complete API response
        expand_config (dict or list): Expansion configuration from the API config
        
    Returns:
        list: List of items with processed expanded fields
    """
    if not expand_config or not items:
        return items
        
    # Process dictionary format (e.g., DeliveryGroup: [Id], MachineCatalog: [Id])
    if isinstance(expand_config, dict):
        for item in items:
            for parent_field, fields in expand_config.items():
                # Prima cerchiamo nell'intera risposta dell'API per collezioni correlate
                parent_collection = parent_field + 's'  # e.g., DeliveryGroups
                if parent_collection in response and isinstance(response[parent_collection], list):
                    parent_id_field = f"{parent_field}Uid"  # e.g., DeliveryGroupUid
                    
                    if parent_id_field in item:
                        parent_id = item[parent_id_field]
                        for related_entity in response[parent_collection]:
                            if related_entity.get('Id') == parent_id:
                                # Create dictionary for expanded field if it doesn't exist
                                if parent_field not in item:
                                    item[parent_field] = {}
                                    
                                # Add fields requested in expansion
                                for field in fields:
                                    if field in related_entity:
                                        item[parent_field][field] = related_entity[field]
                                
                                logging.debug(f"Added expanded field {parent_field} with {len(fields)} attributes from response collection")
                                break
                else:
                    # Se non troviamo collezioni correlate, cerchiamo i campi nested nel item stesso
                    # Per le API Rest i campi expanded sono spesso già presenti ma in forma piatta (es: DeliveryGroupId invece di DeliveryGroup.Id)
                    flattened_fields = {}
                    
                    # Cerchiamo campi con pattern "ParentField + FieldName"
                    for field in fields:
                        flattened_field_name = f"{parent_field}{field}"
                        if flattened_field_name in item:
                            if parent_field not in item:
                                item[parent_field] = {}
                            
                            item[parent_field][field] = item[flattened_field_name]
                            flattened_fields[field] = item[flattened_field_name]
                    
                    if flattened_fields:
                        logging.debug(f"Extracted {len(flattened_fields)} nested fields for {parent_field} from flattened structure")
    
    # Process list format (e.g., ["AssociatedDeliveryGroup"])
    elif isinstance(expand_config, list):
        for item in items:
            for field_name in expand_config:
                # Il campo potrebbe già esistere nell'elemento
                if field_name in item:
                    # Field already exists, make sure it's in correct format
                    if isinstance(item[field_name], list) or isinstance(item[field_name], dict):
                        logging.debug(f"Field {field_name} is already in correct format")
                        continue
                
                # Cercare il campo nel payload principale
                # Prova a capire l'entity type dal nome del campo eliminando eventuali prefissi come "Associated"
                entity_type = field_name.replace('Associated', '')
                entity_collection = entity_type + 's'  # es: DeliveryGroups
                
                if entity_collection in response and isinstance(response[entity_collection], list):
                    # Trova tutte le entità associate
                    associated_ids = item.get(field_name, [])
                    if not isinstance(associated_ids, list):
                        associated_ids = [associated_ids]
                        
                    # Crea una lista di entità associate
                    associated_entities = {}
                    for entity_id in associated_ids:
                        for entity in response[entity_collection]:
                            if entity.get('Id') == entity_id:
                                associated_entities[entity_id] = entity
                                break
                    
                    # Aggiungi le entità associate all'item
                    if associated_entities:
                        # Aggiungi un nuovo campo con le entità associate complete
                        associated_field = entity_type + 's'  # es: DeliveryGroups
                        item[associated_field] = list(associated_entities.values())
                        logging.debug(f"Added {len(associated_entities)} associated entities to {associated_field}")
                
    return items
