import asyncio
import httpx
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from app.utils.config import CONFIG, logger
from app.models.models import SessionEvent


class VictoriaMetricsService:
    """
    Servizio per interrogare VictoriaMetrics e trasformare i dati delle sessioni
    """
    def __init__(self):
        self.base_url = CONFIG.VICTORIA_METRICS_URL
        
    async def get_session_data(self, session_guid: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[SessionEvent]:
        """
        Recupera dati di sessione da VictoriaMetrics e applica trasformazioni simili a Splunk
        
        Args:
            session_guid: GUID della sessione da interrogare
            start_date: Data di inizio opzionale (default: 24 ore prima della fine)
            end_date: Data di fine opzionale (default: ora attuale)
        
        Returns:
            List[SessionEvent]: Lista di eventi della sessione trasformati
        """
        # Imposta date di default se non fornite
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(hours=24)
            
        # Formatta le date per l'API di VictoriaMetrics
        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())
        
        # Questa è la query che estrae i dati base della sessione
        session_query = f'''
        citrix_session{{sessionId="{session_guid}"}}[{start_ts}:{end_ts}]
        '''

        try:
            # Esegui la query a VictoriaMetrics
            raw_data = await self._execute_query(session_query)
            
            if not raw_data or not raw_data.get('data', {}).get('result'):
                logger.warning(f"Nessun dato trovato per la sessione {session_guid}")
                return []
                
            # Trasforma i dati grezzi in un DataFrame per facilitare la manipolazione
            df = self._transform_to_dataframe(raw_data)
            
            # Applica le trasformazioni simili a quelle della query Splunk
            events = self._apply_splunk_like_transformations(df, session_guid)
            
            # Recupera anche i dati di logon/logoff
            logon_events = await self._get_logon_events(session_guid, start_ts, end_ts)
            logoff_events = await self._get_logoff_events(session_guid, start_ts, end_ts)
            
            # Combina tutti gli eventi in ordine cronologico
            all_events = events + logon_events + logoff_events
            all_events.sort(key=lambda x: x.time, reverse=True)
            
            return all_events
            
        except Exception as e:
            logger.error(f"Errore durante l'interrogazione di VictoriaMetrics: {str(e)}")
            return []
    
    async def _execute_query(self, query: str) -> Dict[str, Any]:
        """
        Esegue una query PromQL contro VictoriaMetrics
        
        Args:
            query: Query PromQL da eseguire
            
        Returns:
            Dict: Risultato della query
        """
        endpoint = f"{self.base_url}/api/v1/query_range"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    endpoint,
                    params={
                        "query": query,
                        "step": "60s"  # intervallo di campionamento di un minuto
                    }
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Errore HTTP durante la query: {e}")
                return {}
            except Exception as e:
                logger.error(f"Errore durante la query: {str(e)}")
                return {}
    
    def _transform_to_dataframe(self, raw_data: Dict[str, Any]) -> pd.DataFrame:
        """
        Trasforma i dati grezzi da VictoriaMetrics in un DataFrame pandas
        
        Args:
            raw_data: Dati grezzi da VictoriaMetrics
            
        Returns:
            pd.DataFrame: DataFrame con i dati trasformati
        """
        # Estrai i risultati
        results = raw_data.get('data', {}).get('result', [])
        
        rows = []
        for result in results:
            metric = result.get('metric', {})
            values = result.get('values', [])
            
            for timestamp, value in values:
                # Crea una riga per ogni punto dati
                row = {
                    'time': datetime.fromtimestamp(timestamp),
                    'value': float(value) if value else None,
                    **metric  # Aggiungi tutte le etichette delle metriche come colonne
                }
                rows.append(row)
        
        if not rows:
            # Restituisci un DataFrame vuoto ma con le colonne necessarie
            return pd.DataFrame(columns=['time', 'value', 'clientName', 'clientAddress',
                                        'clientPlatform', 'clientVersion', 'connectionState'])
        
        # Crea il DataFrame
        df = pd.DataFrame(rows)
        
        # Rinomina le colonne per adattarle al formato atteso
        rename_map = {
            'userName': 'userName',
            'clientName': 'clientName',
            'clientAddress': 'clientAddress',
            'clientPlatform': 'clientPlatform', 
            'clientVersion': 'clientVersion',
            'connectionState': 'connectionState'
        }
        
        # Applica rinominazione solo per le colonne che esistono
        rename_map = {k: v for k, v in rename_map.items() if k in df.columns}
        if rename_map:
            df = df.rename(columns=rename_map)
        
        # Assicurati che tutte le colonne necessarie esistano
        for col in ['clientName', 'clientAddress', 'clientPlatform', 'clientVersion', 'connectionState']:
            if col not in df.columns:
                df[col] = None
                
        return df
    
    def _apply_splunk_like_transformations(self, df: pd.DataFrame, session_guid: str) -> List[SessionEvent]:
        """
        Applica trasformazioni simili a quelle della query Splunk sui dati
        
        Args:
            df: DataFrame con i dati della sessione
            session_guid: GUID della sessione
            
        Returns:
            List[SessionEvent]: Eventi trasformati
        """
        if df.empty:
            return []
            
        # Ordina per timestamp
        df = df.sort_values('time')
        
        # Raggruppa per minuto come nella query Splunk
        df['minute'] = df['time'].dt.floor('min')
        
        # Latest per ogni minuto
        latest_df = df.groupby('minute').agg({
            'clientName': 'last',
            'clientAddress': 'last',
            'clientPlatform': 'last',
            'clientVersion': 'last',
            'connectionState': 'last',
            'time': 'last'
        }).reset_index()
        
        # Filtra per stato connessione attiva o campi nulli come nella query Splunk
        mask = (latest_df['connectionState'] == 'Active') | (
            latest_df['clientName'].isna() &
            latest_df['clientAddress'].isna() &
            latest_df['clientPlatform'].isna() &
            latest_df['clientVersion'].isna()
        )
        latest_df = latest_df[mask]
        
        # Riempi i valori null con l'ultimo valore disponibile (filldown)
        latest_df = latest_df.fillna(method='ffill')
        
        # Calcola i cambiamenti tra una riga e l'altra
        events = []
        prev_row = None
        
        for _, row in latest_df.iterrows():
            if prev_row is not None:
                changes = []
                
                # Controlla i cambiamenti come nella query Splunk
                if row['clientName'] != prev_row['clientName']:
                    changes.append("Client name change")
                if row['clientAddress'] != prev_row['clientAddress']:
                    changes.append("Client IP change")
                if row['clientPlatform'] != prev_row['clientPlatform']:
                    changes.append("Client platform change")
                if row['clientVersion'] != prev_row['clientVersion']:
                    changes.append("Client version change")
                if row['connectionState'] != prev_row['connectionState']:
                    changes.append("Connection state change")
                
                if changes:
                    events.append(SessionEvent(
                        time=row['time'].strftime("%Y-%m-%d %H:%M:%S"),
                        session_changes=changes,
                        client_name=row['clientName'],
                        client_ip=row['clientAddress'],
                        client_platform=row['clientPlatform'],
                        client_version=row['clientVersion'],
                        connection_state=row['connectionState']
                    ))
            
            prev_row = row
        
        return events
    
    async def _get_logon_events(self, session_guid: str, start_ts: int, end_ts: int) -> List[SessionEvent]:
        """
        Recupera gli eventi di logon per la sessione
        
        Args:
            session_guid: GUID della sessione
            start_ts: Timestamp di inizio in formato Unix
            end_ts: Timestamp di fine in formato Unix
            
        Returns:
            List[SessionEvent]: Eventi di logon
        """
        # Query per gli eventi di logon
        query = f'''
        citrix_session_logon{{sessionId="{session_guid}"}}[{start_ts}:{end_ts}]
        '''
        
        try:
            # Esegui la query
            raw_data = await self._execute_query(query)
            
            if not raw_data or not raw_data.get('data', {}).get('result'):
                return []
                
            # Trasforma in DataFrame
            df = self._transform_to_dataframe(raw_data)
            
            if df.empty:
                return []
                
            # Crea eventi di logon
            events = []
            for _, row in df.iterrows():
                events.append(SessionEvent(
                    time=row['time'].strftime("%Y-%m-%d %H:%M:%S"),
                    session_changes=["Session logon"],
                    client_name=row.get('clientName'),
                    client_ip=row.get('clientAddress'),
                    client_platform=row.get('clientPlatform'),
                    client_version=row.get('clientVersion'),
                    connection_state=row.get('connectionState')
                ))
            
            return events
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta degli eventi di logon: {str(e)}")
            return []
    
    async def _get_logoff_events(self, session_guid: str, start_ts: int, end_ts: int) -> List[SessionEvent]:
        """
        Recupera gli eventi di logoff per la sessione
        
        Args:
            session_guid: GUID della sessione
            start_ts: Timestamp di inizio in formato Unix
            end_ts: Timestamp di fine in formato Unix
            
        Returns:
            List[SessionEvent]: Eventi di logoff
        """
        # Query per gli eventi di logoff
        query = f'''
        citrix_session_logoff{{sessionId="{session_guid}"}}[{start_ts}:{end_ts}]
        '''
        
        try:
            # Esegui la query
            raw_data = await self._execute_query(query)
            
            if not raw_data or not raw_data.get('data', {}).get('result'):
                return []
                
            # Trasforma in DataFrame
            df = self._transform_to_dataframe(raw_data)
            
            if df.empty:
                return []
                
            # Crea eventi di logoff
            events = []
            for _, row in df.iterrows():
                events.append(SessionEvent(
                    time=row['time'].strftime("%Y-%m-%d %H:%M:%S"),
                    session_changes=["Session logoff"],
                    client_name=row.get('clientName'),
                    client_ip=row.get('clientAddress'),
                    client_platform=row.get('clientPlatform'),
                    client_version=row.get('clientVersion'),
                    connection_state=row.get('connectionState')
                ))
            
            return events
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta degli eventi di logoff: {str(e)}")
            return []


# Singoletto del servizio VictoriaMetrics
victoria_metrics_service = VictoriaMetricsService()