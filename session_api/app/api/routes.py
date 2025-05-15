from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime

from app.models.models import SessionRequest, SessionResponse
from app.api.victoria_service import victoria_metrics_service
from app.utils.config import logger

router = APIRouter()

@router.get("/session/{session_guid}")
async def get_session_events(
    session_guid: str,
    start_date: Optional[datetime] = Query(None, description="Data di inizio (formato ISO)"),
    end_date: Optional[datetime] = Query(None, description="Data di fine (formato ISO)")
):
    """
    Recupera gli eventi di una sessione tramite il suo GUID.
    
    Args:
        session_guid: GUID della sessione da interrogare
        start_date: Data di inizio opzionale (formato ISO)
        end_date: Data di fine opzionale (formato ISO)
    
    Returns:
        SessionResponse: Dati della sessione e relativi eventi
    """
    logger.info(f"Richiesta dati per la sessione {session_guid} dal {start_date} al {end_date}")
    
    try:
        # Recupera i dati dalla sessione tramite VictoriaMetrics
        events = await victoria_metrics_service.get_session_data(session_guid, start_date, end_date)
        
        # Prepara la risposta
        response = SessionResponse(
            session_guid=session_guid,
            events=events,
            metadata={
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "total_events": len(events)
            }
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Errore durante l'elaborazione della richiesta per la sessione {session_guid}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante l'elaborazione della richiesta: {str(e)}"
        )

@router.post("/session")
async def post_session_events(request: SessionRequest):
    """
    Recupera gli eventi di una sessione tramite richiesta POST.
    
    Args:
        request: Richiesta con GUID della sessione e date opzionali
    
    Returns:
        SessionResponse: Dati della sessione e relativi eventi
    """
    logger.info(f"Richiesta POST dati per la sessione {request.session_guid}")
    
    try:
        # Recupera i dati dalla sessione tramite VictoriaMetrics
        events = await victoria_metrics_service.get_session_data(
            request.session_guid,
            request.start_date,
            request.end_date
        )
        
        # Prepara la risposta
        response = SessionResponse(
            session_guid=request.session_guid,
            events=events,
            metadata={
                "start_date": request.start_date.isoformat() if request.start_date else None,
                "end_date": request.end_date.isoformat() if request.end_date else None,
                "total_events": len(events)
            }
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Errore durante l'elaborazione della richiesta POST per la sessione {request.session_guid}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante l'elaborazione della richiesta: {str(e)}"
        )