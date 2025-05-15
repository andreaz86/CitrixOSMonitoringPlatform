from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class SessionRequest(BaseModel):
    """
    Modello per la richiesta di dati di sessione
    """
    session_guid: str = Field(..., description="GUID della sessione da interrogare")
    start_date: Optional[datetime] = Field(
        None, 
        description="Data di inizio per il filtro (formato ISO)"
    )
    end_date: Optional[datetime] = Field(
        None, 
        description="Data di fine per il filtro (formato ISO)"
    )


class SessionEvent(BaseModel):
    """
    Modello per un singolo evento di sessione
    """
    time: str = Field(..., description="Timestamp dell'evento")
    session_changes: List[str] = Field(..., description="Cambiamenti rilevati nella sessione")
    client_name: Optional[str] = Field(None, description="Nome del client")
    client_ip: Optional[str] = Field(None, description="Indirizzo IP del client")
    client_platform: Optional[str] = Field(None, description="Piattaforma del client")
    client_version: Optional[str] = Field(None, description="Versione del client")
    connection_state: Optional[str] = Field(None, description="Stato della connessione")


class SessionResponse(BaseModel):
    """
    Modello per la risposta con i dati di sessione
    """
    session_guid: str = Field(..., description="GUID della sessione interrogata")
    events: List[SessionEvent] = Field(default_factory=list, description="Eventi della sessione")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadati aggiuntivi")