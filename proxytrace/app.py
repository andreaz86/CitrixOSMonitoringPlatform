import socket
import threading
import queue
import signal
import time
import os
import logging
import orjson
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import pybreaker
from prometheus_client import start_http_server, Counter, Gauge, Summary
from influxdb_client import InfluxDBClient, Point, WriteOptions

# ---------------------- Configuration ----------------------
LISTEN_HOST = os.getenv('LISTEN_HOST', '0.0.0.0')
LISTEN_PORT = int(os.getenv('LISTEN_PORT', 5000))
METRICS_PORT = int(os.getenv('METRICS_PORT', 8000))
OTLP_ENDPOINT = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://jaeger:4318/v1/traces')
WORKER_COUNT = int(os.getenv('WORKER_COUNT', 8))
BATCH_SIZE = int(os.getenv('BATCH_SIZE', 200))
BATCH_TIMEOUT = float(os.getenv('BATCH_TIMEOUT', 0.2))  # seconds
QUEUE_MAXSIZE = int(os.getenv('QUEUE_MAXSIZE', 10000))
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() in ('true', '1', 'yes')

# InfluxDB config
INFLUX_URL = os.getenv('INFLUX_URL', 'http://victoriametrics:8428')
INFLUX_TOKEN = os.getenv('INFLUX_TOKEN', '')
INFLUX_ORG = os.getenv('INFLUX_ORG', '')
INFLUX_BUCKET = os.getenv('INFLUX_BUCKET', 'traces')

# ---------------------- Logging ----------------------
logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)
logger.info(f"Debug mode: {'enabled' if DEBUG_MODE else 'disabled'}")

# ---------------------- Metrics ----------------------
records_received = Counter('records_received_total', 'Total records received')
records_parsed = Counter('records_parsed_total', 'Total records parsed into spans')
batches_sent = Counter('batches_sent_total', 'Total batches successfully sent')
export_failures = Counter('export_failures_total', 'Total batch export failures')
span_queue_size = Gauge('span_queue_size', 'Current size of the span queue')
batch_latency = Summary('batch_latency_seconds', 'Time spent sending batch')

# ---------------------- Queues & Shutdown ----------------------
recv_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
span_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
shutdown_event = threading.Event()

# ---------------------- Circuit Breaker ----------------------
breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=30)

# ---------------------- HTTP Session with Retry ----------------------
session = Session()
retries = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504]
)
adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
session.mount('http://', adapter)
session.mount('https://', adapter)

# ---------------------- InfluxDB Client ----------------------
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx_client.write_api(write_options=WriteOptions(batch_size=1000, flush_interval=1000))

# ---------------------- Span Builder ----------------------
def build_span(record: dict) -> dict:
    epoch_s = int(time.time())
    start_ns = epoch_s * 1_000_000_000 + int(record.get('ProcStartTimeRelativeMs', 0)) * 1_000_000
    end_ns = start_ns + int(record.get('ProcLifetimeMs', 0)) * 1_000_000

    span_id = format(int(record.get('ProcID', 0)), '016x')
    parent_id = ''
    if int(record.get('ProcParentID', 0)):
        parent_id = format(int(record.get('ProcParentID', 0)), '016x')
    
    is_logoff = 'LogoffProcType' in record
    service_name = record.get('LogoffProcType', record.get('LogonProcType', 'unknown-service')) if is_logoff else record.get('LogonProcType', 'unknown-service')
    event_type = "logoff" if is_logoff else "logon"
    guid = record.get('SessionGUID', '')
    base_trace = guid.replace('-', '')
    if is_logoff:
        trace_id = ('2' + base_trace + '0'*31)[:32]
    else:
        trace_id = ('1' + base_trace + '0'*31)[:32]

    return {
        '_guid': guid,
        '_trace_id': trace_id,
        'resourceSpans': [
            {
                'resource': {
                    'attributes': [
                        {'key': 'service.name', 'value': {'stringValue': service_name}}
                    ]
                },
                'scopeSpans': [
                    {
                        'spans': [
                            {
                                'traceId': trace_id,
                                'spanId': span_id,
                                'parentSpanId': parent_id,
                                'name': record.get('ProcName', 'unknown-span'),
                                'kind': 'SPAN_KIND_INTERNAL',
                                'startTimeUnixNano': str(start_ns),
                                'endTimeUnixNano': str(end_ns),
                                'attributes': [
                                    {'key': 'ProcUser', 'value': {'stringValue': record.get('ProcUser', 'unknown-user')}},
                                    {'key': 'ProcCPUTimeMs', 'value': {'intValue': int(record.get('ProcCPUTimeMs', 0))}},
                                    {'key': 'ProcWorkingSetMB', 'value': {'doubleValue': float(record.get('ProcWorkingSetMB', 0))}},
                                    {'key': 'ProcNetKBPS', 'value': {'doubleValue': float(record.get('ProcNetKBPS', 0))}},
                                    {'key': 'ProcIOReadCount', 'value': {'intValue': int(record.get('ProcIOReadCount', 0))}},
                                    {'key': 'ProcIOWriteCount', 'value': {'intValue': int(record.get('ProcIOWriteCount', 0))}},
                                    {'key': 'ProcIOReadMB', 'value': {'doubleValue': int(record.get('ProcIOReadMB', 0))}},
                                    {'key': 'ProcIOWriteMB', 'value': {'doubleValue': int(record.get('ProcIOWriteMB', 0))}},
                                    {'key': 'ProcIOLatencyReadMs2', 'value': {'intValue': int(record.get('ProcIOLatencyReadMs2', 0))}},
                                    {'key': 'ProcIOLatencyWriteMs2', 'value': {'intValue': int(record.get('ProcIOLatencyWriteMs2', 0))}},
                                    {'key': 'ProcLifetimeMs', 'value': {'intValue': int(record.get('ProcLifetimeMs', 0))}},
                                    {'key': 'event_type', 'value': {'stringValue': event_type}}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

# ---------------------- Batch Exporter ----------------------
class BatchExporter(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        if DEBUG_MODE:
            logger.debug("BatchExporter initialized in debug mode")

    @breaker
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception)
    )
    @batch_latency.time()
    def send_batch(self, batch):
        if DEBUG_MODE:
            logger.debug(f"Sending batch of {len(batch)} spans to OTLP endpoint")
        
        payload = {'resourceSpans': []}
        for span in batch:
            payload['resourceSpans'].extend(span['resourceSpans'])

        if DEBUG_MODE:
            logger.debug(f"Batch payload contains {len(payload['resourceSpans'])} resourceSpans")
        
        resp = session.post(OTLP_ENDPOINT, json=payload, timeout=5)
        resp.raise_for_status()
        
        if DEBUG_MODE:
            logger.debug(f"Batch sent successfully: {resp.status_code}")
        
        return resp

    def run(self):
        logger.info("BatchExporter thread started")
        while not shutdown_event.is_set():
            batch = []
            try:
                span = span_queue.get(timeout=1)
                batch.append(span)
                start = time.time()
                while len(batch) < BATCH_SIZE and (time.time() - start) < BATCH_TIMEOUT:
                    try:
                        batch.append(span_queue.get(timeout=BATCH_TIMEOUT - (time.time()-start)))
                    except queue.Empty:
                        if DEBUG_MODE:
                            logger.debug(f"Queue empty, proceeding with batch of {len(batch)} spans")
                        break
            except queue.Empty:
                if DEBUG_MODE and span_queue.qsize() > 0:
                    logger.debug(f"Span queue size: {span_queue.qsize()}")
                continue

            if batch:
                if DEBUG_MODE:
                    logger.debug(f"Processing batch of {len(batch)} spans")
                try:
                    self.send_batch(batch)
                    batches_sent.inc()
                    seen = {}
                    for s in batch:
                        g = s.get('_guid')
                        t = s.get('_trace_id')
                        if g and t:
                            seen[g] = t
                    ts = int(time.time() * 1e9)
                    
                    if DEBUG_MODE:
                        logger.debug(f"Writing {len(seen)} unique guid->trace_id mappings to InfluxDB")
                        
                    for g, t in seen.items():
                        metric_name = "uberAgent:logonTraceMap" if t.startswith('1') else "uberAgent:logoffTraceMap"
                        p = Point(metric_name).tag("guid", g).tag("trace_id", t).field("value", 0).time(ts)
                        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)
                        
                        if DEBUG_MODE:
                            logger.debug(f"Metric written: {metric_name}, GUID: {g}, Trace ID: {t}, Timestamp: {ts}")
                        
                        if DEBUG_MODE:
                            logger.debug(f"Wrote mapping for GUID {g} -> trace_id {t}")
                except Exception as e:
                    logger.error(f"Batch export failed: {e}")
                    if DEBUG_MODE:
                        logger.exception("Detailed export error")
                    export_failures.inc()
            span_queue_size.set(span_queue.qsize())

# ---------------------- Worker ----------------------
def worker():
    while not shutdown_event.is_set():
        try:
            line = recv_queue.get(timeout=1)
        except queue.Empty:
            continue

        records_received.inc()
        try:
            record = orjson.loads(line)
            span = build_span(record)
            records_parsed.inc()
            span_queue.put(span)
        except Exception as e:
            logger.error(f"Failed to parse record: {e}")
        span_queue_size.set(span_queue.qsize())

# ---------------------- Socket Reader ----------------------
def handle_client(sock, addr):
    logger.info(f"Connection from {addr}")
    buf = b''
    try:
        while not shutdown_event.is_set():
            data = sock.recv(4096)
            if not data:
                break
            buf += data
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                if line.strip():
                    recv_queue.put(line)
    except Exception as e:
        logger.error(f"Client error {addr}: {e}")
    finally:
        sock.close()


def socket_listener():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen()
    logger.info(f"Listening on {LISTEN_HOST}:{LISTEN_PORT}")
    while not shutdown_event.is_set():
        try:
            server.settimeout(1)
            client, addr = server.accept()
            threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
        except socket.timeout:
            continue
    server.close()

# ---------------------- Graceful Shutdown ----------------------
def shutdown(signum, frame):
    logger.info("Shutdown signal received")
    shutdown_event.set()

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ---------------------- Main ----------------------
if __name__ == '__main__':
    start_http_server(METRICS_PORT)
    logger.info(f"Metrics HTTP server running on :{METRICS_PORT}")

    exporter = BatchExporter()
    exporter.start()

    for _ in range(WORKER_COUNT):
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    socket_listener()

    logger.info("Waiting for queues to drain...")
    while not recv_queue.empty() or not span_queue.empty():
        time.sleep(1)
    logger.info("Shutdown complete")
