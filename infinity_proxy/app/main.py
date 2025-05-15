from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import httpx
import os
import re
import logging
import ssl
import time
import json
import traceback
from typing import Dict, Any, Optional

# Importare le librerie OpenTelemetry per il tracciamento
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# Configure logging
log_level = logging.DEBUG if os.getenv("DEBUG", "false").lower() in ("true", "1", "yes") else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("citrix_proxy")

# Log startup configuration
logger.info("Starting Citrix Cloud Proxy Middleware")
logger.info(f"Log level set to: {logging.getLevelName(log_level)}")

# Setup OpenTelemetry tracing
JAEGER_ENABLED = os.getenv("JAEGER_ENABLED", "false").lower() in ("true", "1", "yes")
JAEGER_HOST = os.getenv("JAEGER_HOST", "jaeger")
JAEGER_PORT = os.getenv("JAEGER_PORT", "4317")

if JAEGER_ENABLED:
    logger.info(f"OpenTelemetry tracing enabled, sending spans to {JAEGER_HOST}:{JAEGER_PORT}")
    
    # Configure the tracer
    resource = Resource.create({"service.name": "infinity_proxy"})
    tracer_provider = TracerProvider(resource=resource)
    
    # Configure the OTLP exporter
    otlp_endpoint = f"http://{JAEGER_HOST}:{JAEGER_PORT}"
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    
    # Add span processor
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)
    
    # Set the tracer provider
    trace.set_tracer_provider(tracer_provider)
    
    # Get a tracer
    tracer = trace.get_tracer("infinity_proxy.tracer")
else:
    logger.info("OpenTelemetry tracing disabled")
    tracer = None

app = FastAPI(title="Citrix Cloud Proxy Middleware")

# Read configuration from environment variables
DEFAULT_TARGET_HOST = os.getenv("DEFAULT_TARGET_HOST", "https://api.cloud.com")
TARGET_HOST = os.getenv("TARGET_HOST", "api.cloud.com")
DEBUG_MODE = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

if DEBUG_MODE:
    logger.debug("DEBUG_MODE is enabled - verbose logging will be active")
    logger.debug(f"Configuration: DEFAULT_TARGET_HOST={DEFAULT_TARGET_HOST}, TARGET_HOST={TARGET_HOST}")

# Function to get proxy URL from environment variables, supporting both uppercase and lowercase
def get_proxy_url() -> Optional[str]:
    """
    Get proxy configuration from environment variables.
    Supports both HTTP_PROXY/HTTPS_PROXY and http_proxy/https_proxy formats.
    Returns None if no proxy is configured.
    """
    # Check for HTTP_PROXY in uppercase or lowercase
    proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if proxy:
        logger.info(f"Using proxy: {proxy}")
        return proxy
    
    logger.info("No proxy configured, connecting directly")
    return None


async def modify_request(request: Request) -> Dict[str, Any]:
    """Modify the request headers before forwarding."""
    headers = dict(request.headers)
    
    if DEBUG_MODE:
        logger.debug(f"Original request headers: {headers}")
    
    # Rewrite Authorization header (similar to Nginx rewrite)
    auth_header = headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        # Extract the token and reformat it
        token = re.match(r"^Bearer (.+)$", auth_header)
        if token:
            headers["authorization"] = f"CwsAuth Bearer {token.group(1)}"
            logger.info("Transformed Bearer token to CwsAuth Bearer token")
            if DEBUG_MODE:
                logger.debug("Authorization header transformed successfully")
    
    # Set Host header to match Nginx proxy_set_header Host value
    headers["host"] = TARGET_HOST
    if DEBUG_MODE:
        logger.debug(f"Set Host header to: {TARGET_HOST}")
    
    # Keep Citrix-CustomerId header as is (equivalent to set $citrix_customerid $http_citrix_customerid)
    if "citrix-customerid" in headers:
        logger.info(f"Found Citrix-CustomerId header: {headers['citrix-customerid']}")
    
    # Ensure Accept header is set (equivalent to proxy_set_header Accept application/json)
    headers["accept"] = "application/json"
    if DEBUG_MODE:
        logger.debug("Set Accept header to: application/json")
    
    # Clean up any headers we don't want to forward
    if "content-length" in headers:
        if DEBUG_MODE:
            logger.debug("Removing content-length header from request")
        del headers["content-length"]
    
    # Add X-Forwarded headers if needed
    remote_addr = request.client.host if request.client else "unknown"
    if "x-forwarded-for" in headers:
        headers["x-forwarded-for"] = f"{headers['x-forwarded-for']}, {remote_addr}"
        if DEBUG_MODE:
            logger.debug(f"Appended client IP to X-Forwarded-For: {headers['x-forwarded-for']}")
    else:
        headers["x-forwarded-for"] = remote_addr
        if DEBUG_MODE:
            logger.debug(f"Set X-Forwarded-For header to: {remote_addr}")
    
    if DEBUG_MODE:
        logger.debug(f"Modified headers: {headers}")
    return headers


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_endpoint(request: Request, path: str):
    """
    Main proxy endpoint that handles all incoming requests and forwards them to the target.
    Rewrites authentication headers before forwarding and sets all required headers.
    """
    request_id = f"req-{int(time.time() * 1000)}"
    current_span = None
    
    # Create a span for this request if tracing is enabled
    if JAEGER_ENABLED and tracer:
        with tracer.start_as_current_span(
            name=f"{request.method} /{path}",
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
                "http.target": f"/{path}",
                "http.request_id": request_id,
                "http.client_ip": request.client.host if request.client else "unknown",
            }
        ) as span:
            current_span = span
            # Proceed with the request handling
            return await handle_request(request, path, request_id, current_span)
    else:
        # If tracing is disabled, just handle the request normally
        return await handle_request(request, path, request_id, None)


async def handle_request(request: Request, path: str, request_id: str, span: Optional[trace.Span] = None):
    """
    Handle the proxy request logic, with optional tracing span support.
    """
    # Log request details if in debug mode
    if DEBUG_MODE:
        logger.debug(f"[{request_id}] Received request: {request.method} {request.url.path}")
        logger.debug(f"[{request_id}] Query parameters: {dict(request.query_params)}")
        logger.debug(f"[{request_id}] Client IP: {request.client.host if request.client else 'unknown'}")
    
    # Create an SSL context that allows for SNI (equivalent to proxy_ssl_server_name on)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = True
    
    # Get proxy configuration from environment variables
    proxies = get_proxy_url()
    
    # Create client with the correct configurations for handling compressed responses
    try:
        # Don't use proxy for Jaeger/OpenTelemetry requests
        target_host = request.url.hostname or TARGET_HOST
        if JAEGER_ENABLED and target_host == JAEGER_HOST:
            proxy_config = None
            if DEBUG_MODE:
                logger.debug(f"[{request_id}] Skipping proxy for Jaeger request to {target_host}")
        else:
            proxy_config = {"http://": proxies, "https://": proxies} if proxies else None

        client = httpx.AsyncClient(
            http2=True,
            verify=ssl_context,  # Use custom SSL context that enables SNI
            proxies=proxy_config,
            timeout=httpx.Timeout(
                connect=10.0,    # Maximum time to establish connection
                read=30.0,       # Maximum time to read data
                write=10.0,      # Maximum time to write data
                pool=30.0        # Maximum time to wait for a connection from the pool
            )
        )
        
        if proxies:
            logger.info(f"[{request_id}] Created client with proxy configuration: {proxies}")
        
        # Initialize HTTPX instrumentation if tracing is enabled
        if JAEGER_ENABLED and span is not None:
            HTTPXClientInstrumentor().instrument_client(client)
        
        if DEBUG_MODE:
            logger.debug(f"[{request_id}] Client created successfully with timeout settings")
    except Exception as e:
        error_msg = f"Failed to create HTTP client: {str(e)}"
        logger.error(f"[{request_id}] {error_msg}")
        if span is not None:
            span.set_attribute("error", True)
            span.set_attribute("error.message", error_msg)
        return Response(content=error_msg, status_code=500)
    
    # Get the target URL
    target_url = f"{DEFAULT_TARGET_HOST}/{path}"
    if request.query_params:
        target_url += f"?{request.url.query}"
        
    if DEBUG_MODE:
        logger.debug(f"[{request_id}] Forwarding to target URL: {target_url}")
    
    if span is not None:
        span.set_attribute("http.target_url", target_url)
    
    # Get the request body
    body = await request.body()
    if DEBUG_MODE and body:
        body_size = len(body)
        logger.debug(f"[{request_id}] Request body size: {body_size} bytes")
        if body_size < 4096:  # Only log bodies smaller than 4KB to prevent log flooding
            try:
                # Try to decode as JSON for nicer logging
                try:
                    json_body = json.loads(body)
                    logger.debug(f"[{request_id}] Request body (JSON): {json.dumps(json_body, indent=2)}")
                except json.JSONDecodeError:
                    # Not JSON, log as text if possible
                    try:
                        text_body = body.decode('utf-8')
                        logger.debug(f"[{request_id}] Request body (text): {text_body}")
                    except UnicodeDecodeError:
                        logger.debug(f"[{request_id}] Request body is binary data (not logged)")
            except Exception as e:
                logger.debug(f"[{request_id}] Error while logging request body: {str(e)}")
    
    # Get and modify headers
    headers = await modify_request(request)
    
    start_time = time.time()
    
    try:
        # Forward the request to the target
        if DEBUG_MODE:
            logger.debug(f"[{request_id}] Sending {request.method} request to {target_url}")
        
        if span is not None:
            span.add_event("sending_request")
        
        response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            follow_redirects=True,
        )
        
        elapsed = time.time() - start_time
        
        if span is not None:
            span.add_event("received_response")
            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute("http.response_time", elapsed)
        
        if DEBUG_MODE:
            logger.debug(f"[{request_id}] Received response from {target_url} in {elapsed:.3f}s: status={response.status_code}")
            logger.debug(f"[{request_id}] Response headers: {dict(response.headers)}")
        
        # Read the content first to prevent StreamConsumed error
        content = await response.aread()
        
        if span is not None:
            span.set_attribute("http.response_size", len(content))
        
        if DEBUG_MODE and content:
            content_size = len(content)
            logger.debug(f"[{request_id}] Response content size: {content_size} bytes")
            if content_size < 4096:  # Only log responses smaller than 4KB
                try:
                    # Try to decode as JSON for nicer logging
                    try:
                        json_content = json.loads(content)
                        logger.debug(f"[{request_id}] Response content (JSON): {json.dumps(json_content, indent=2)}")
                    except json.JSONDecodeError:
                        # Not JSON, log as text if possible
                        try:
                            text_content = content.decode('utf-8')
                            # Log only first 1000 chars to avoid flooding logs
                            if len(text_content) > 1000:
                                text_content = text_content[:1000] + "... [truncated]"
                            logger.debug(f"[{request_id}] Response content (text): {text_content}")
                        except UnicodeDecodeError:
                            logger.debug(f"[{request_id}] Response content is binary data (not logged)")
                except Exception as e:
                    logger.debug(f"[{request_id}] Error while logging response content: {str(e)}")
        
        # Process response headers
        response_headers = dict(response.headers)
        
        # Remove problematic headers that might interfere with encoding
        headers_to_remove = ["content-length", "content-encoding", "transfer-encoding"]
        for header in headers_to_remove:
            if header in response_headers:
                if DEBUG_MODE:
                    logger.debug(f"[{request_id}] Removing header: {header}")
                del response_headers[header]
        
        # Create response with the same status code and modified headers
        # The content is already decompressed by httpx, so we send it as-is
        if DEBUG_MODE:
            logger.debug(f"[{request_id}] Sending response back to client with status {response.status_code}")
            
        return Response(
            content=content,
            status_code=response.status_code,
            headers=response_headers,
        )
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{request_id}] Error forwarding request after {elapsed:.3f}s: {str(e)}")
        
        if span is not None:
            span.record_exception(e)
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
        
        if DEBUG_MODE:
            logger.debug(f"[{request_id}] Error details:\n{traceback.format_exc()}")
        return Response(content=str(e), status_code=500)
    finally:
        await client.aclose()
        if DEBUG_MODE:
            total_elapsed = time.time() - start_time
            logger.debug(f"[{request_id}] Request completed in {total_elapsed:.3f}s")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    if DEBUG_MODE:
        logger.debug("Health check requested")
    return {"status": "ok"}


# Instrumenta l'app FastAPI con OpenTelemetry se il tracing è abilitato
if JAEGER_ENABLED:
    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI instrumented with OpenTelemetry")
