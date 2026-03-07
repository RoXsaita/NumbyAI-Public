"""
Structured Logger for Finance App (Python)

Provides centralized, structured logging for observability.
All logs are output as JSON to enable easy parsing and debugging.

Key features:
1. Structured JSON output (timestamp, level, event, metadata)
2. Tool call tracking (start, end, error)
3. Error taxonomy (TIMEOUT, VALIDATION_ERROR, DB_ERROR, etc.)
4. Duration tracking for performance monitoring

This mirrors the TypeScript logger in shared/logger.ts for consistency.
"""

import json
import sys
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Literal, Optional, Union
from contextlib import contextmanager


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================================
# TYPES
# ============================================================================

class LogLevel(str, Enum):
    """Log level enumeration"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class ErrorType(str, Enum):
    """Standard error types for consistent error handling"""
    VALIDATION_ERROR = "VALIDATION_ERROR"    # Schema validation failed
    TIMEOUT = "TIMEOUT"                       # Request/operation timed out
    NETWORK_ERROR = "NETWORK_ERROR"           # Network/HTTP error
    DB_ERROR = "DB_ERROR"                     # Database operation failed
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"     # OpenAI tool not available
    WRITE_DISABLED = "WRITE_DISABLED"         # Write operations disabled
    PARSE_ERROR = "PARSE_ERROR"               # Data parsing failed
    UNKNOWN_ERROR = "UNKNOWN_ERROR"           # Unexpected error


# ============================================================================
# LOGGER CLASS
# ============================================================================

class Logger:
    """Structured logger with JSON output"""

    def __init__(self, context: Optional[str] = None):
        self.context = context

    def with_context(self, context: str) -> "Logger":
        """Create a child logger with a specific context"""
        return Logger(context)

    def _log(
        self,
        level: LogLevel,
        event: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a structured message"""
        entry = {
            "timestamp": _utc_now_iso(),
            "level": level.value,
            "event": event,
        }

        if self.context:
            entry["context"] = self.context

        if metadata:
            entry["metadata"] = metadata

        # Output as pretty-printed JSON for readability
        output = json.dumps(entry, indent=2, default=str)

        # Route to appropriate stream
        if level in (LogLevel.ERROR, LogLevel.WARN):
            print(output, file=sys.stderr, flush=True)
        else:
            print(output, file=sys.stdout, flush=True)

    def debug(self, event: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log debug message"""
        self._log(LogLevel.DEBUG, event, metadata)

    def info(self, event: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log info message"""
        self._log(LogLevel.INFO, event, metadata)

    def warn(self, event: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log warning message"""
        self._log(LogLevel.WARN, event, metadata)

    def error(self, event: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log error message"""
        self._log(LogLevel.ERROR, event, metadata)

    def tool_call_start(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> str:
        """Log the start of a tool call, returns timestamp for duration tracking"""
        started_at = _utc_now_iso()

        metadata = {
            "tool_name": tool_name,
            "started_at": started_at,
        }
        if args:
            metadata["arguments"] = args

        self.info("Tool call started", metadata)
        return started_at

    def tool_call_end(
        self,
        tool_name: str,
        started_at: str,
        result: Optional[Any] = None,
    ) -> None:
        """Log successful tool call completion"""
        ended_at = _utc_now_iso()
        start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        duration_ms = int((end_dt - start_dt).total_seconds() * 1000)

        metadata = {
            "tool_name": tool_name,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "success": True,
        }
        if result is not None:
            metadata["result_summary"] = self._summarize_result(result)

        self.info("Tool call completed", metadata)

    def tool_call_error(
        self,
        tool_name: str,
        started_at: str,
        error: Exception,
        error_type: ErrorType = ErrorType.UNKNOWN_ERROR,
    ) -> None:
        """Log tool call error"""
        ended_at = _utc_now_iso()
        start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        duration_ms = int((end_dt - start_dt).total_seconds() * 1000)

        metadata = {
            "tool_name": tool_name,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "success": False,
            "error_type": error_type.value,
            "error_message": str(error),
        }

        self.error("Tool call failed", metadata)

    def validation_error(
        self,
        validation_context: str,
        error: Exception,
        data: Optional[Any] = None,
    ) -> None:
        """Log a validation error with details"""
        metadata = {
            "validation_context": validation_context,
            "error": str(error),
        }
        if data is not None:
            metadata["invalid_data"] = self._summarize_result(data)

        self.error("Validation failed", metadata)

    def _summarize_result(self, result: Any) -> Any:
        """Summarize result for logging (avoid logging huge objects)"""
        if result is None:
            return None

        if isinstance(result, (list, tuple)):
            return {
                "_type": "array",
                "length": len(result),
                "sample": result[:3] if result else [],
            }

        if isinstance(result, dict):
            return {
                "_type": "object",
                "keys": list(result.keys())[:10],
            }

        # For simple types, return as-is
        if isinstance(result, (str, int, float, bool)):
            return result

        # For other objects, just return type
        return {"_type": type(result).__name__}

    @contextmanager
    def tool_call(self, tool_name: str, args: Optional[Dict[str, Any]] = None):
        """Context manager for tool calls with automatic logging"""
        started_at = self.tool_call_start(tool_name, args)
        try:
            yield
            self.tool_call_end(tool_name, started_at)
        except Exception as e:
            error_type = classify_error(e)
            self.tool_call_error(tool_name, started_at, e, error_type)
            raise


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def classify_error(error: Exception) -> ErrorType:
    """Helper to classify errors into ErrorType"""
    error_msg = str(error).lower()

    if "timeout" in error_msg:
        return ErrorType.TIMEOUT
    if "network" in error_msg or "connection" in error_msg:
        return ErrorType.NETWORK_ERROR
    if "validation" in error_msg or "schema" in error_msg:
        return ErrorType.VALIDATION_ERROR
    if "database" in error_msg or "sqlite" in error_msg or "sql" in error_msg:
        return ErrorType.DB_ERROR
    if "parse" in error_msg or "json" in error_msg or "decode" in error_msg:
        return ErrorType.PARSE_ERROR
    if "tool" in error_msg and "unavailable" in error_msg:
        return ErrorType.TOOL_UNAVAILABLE
    if "write" in error_msg and "disabled" in error_msg:
        return ErrorType.WRITE_DISABLED

    return ErrorType.UNKNOWN_ERROR


# ============================================================================
# EXPORTS
# ============================================================================

# Default logger instance
logger = Logger()


def create_logger(context: str) -> Logger:
    """Create a logger with a specific context"""
    return Logger(context)
