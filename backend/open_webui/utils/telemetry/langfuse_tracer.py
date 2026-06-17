"""
Langfuse LLM observability integration for Open WebUI.

Captures LLM completions, tool calls, reasoning, and streaming lifecycle
as structured traces in Langfuse for observability across agent gateways.

Enable via environment variables::

    ENABLE_LANGFUSE=true
    LANGFUSE_SECRET_KEY=sk-lf-...
    LANGFUSE_PUBLIC_KEY=pk-lf-...
    LANGFUSE_HOST=https://cloud.langfuse.com   # or self-hosted URL

Architecture: ONE trace per chat session (chat_id), each user message
appends a "turn" span. This gives a complete conversation timeline in
a single Langfuse trace view.

Span hierarchy::

    Trace  (id = chat_id, name = "chat_session")
    ├── Span  turn_1  (input: user msg 1)
    │   ├── Generation  llm_call
    │   ├── Span        tool:search_web
    │   └── Span        tool:fetch_url
    ├── Span  turn_2  (input: user msg 2)
    │   └── Generation  llm_call
    ├── Span  turn_3  (input: user msg 3)
    │   ├── Generation  llm_call
    │   └── Span        tool:analyze
    └── ...
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from open_webui.env import (
    ENABLE_LANGFUSE,
    LANGFUSE_SECRET_KEY,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_HOST,
    GLOBAL_LOG_LEVEL,
)

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Singleton client
# ──────────────────────────────────────────────────────────────────────
_langfuse_client = None


def get_langfuse():
    """Lazily create and return the singleton Langfuse client.

    Returns ``None`` when Langfuse is disabled or the SDK is missing.
    """
    global _langfuse_client
    if not ENABLE_LANGFUSE:
        return None
    if _langfuse_client is None:
        try:
            from langfuse import Langfuse  # noqa: F811 – lazy import

            _langfuse_client = Langfuse(
                secret_key=LANGFUSE_SECRET_KEY,
                public_key=LANGFUSE_PUBLIC_KEY,
                host=LANGFUSE_HOST,
            )
            log.info('Langfuse client initialised (host=%s)', LANGFUSE_HOST)
        except ImportError:
            log.warning(
                'ENABLE_LANGFUSE is true but the langfuse package is not installed. '
                'Run: pip install langfuse'
            )
        except Exception as e:
            log.error('Failed to initialise Langfuse: %s', e)
    return _langfuse_client


# ──────────────────────────────────────────────────────────────────────
# Trace  –  one per chat session (chat_id)
# ──────────────────────────────────────────────────────────────────────
class LangfuseTrace:
    """Exception-safe wrapper around a Langfuse *trace*.

    Uses a deterministic trace ID (= chat_id) so that every message in
    the same chat session appends to the same trace.  Langfuse upserts
    on the server side: first call creates, subsequent calls merge.
    """

    __slots__ = ('_trace',)

    def __init__(self):
        self._trace = None

    @property
    def enabled(self) -> bool:
        return self._trace is not None

    # ── factory ───────────────────────────────────────────────────────
    @classmethod
    def start(
        cls,
        *,
        trace_id: str,
        name: str = 'chat_session',
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> LangfuseTrace:
        """Get or create a trace for this chat session.

        ``trace_id`` should be the chat_id — Langfuse will upsert so
        all turns in the same conversation land in one trace.
        ``session_id`` can be the same as trace_id (Langfuse uses it
        for grouping in the Sessions view).
        """
        obj = cls()
        client = get_langfuse()
        if client is None:
            return obj
        try:
            obj._trace = client.trace(
                id=trace_id,
                name=name,
                user_id=user_id,
                session_id=session_id,
                metadata=metadata or {},
                tags=tags or [],
            )
        except Exception as e:
            log.warning('Failed to create/get Langfuse trace: %s', e)
        return obj

    # ── turn (one user message → assistant response cycle) ───────────
    def turn(
        self,
        *,
        name: str = 'turn',
        input: Any = None,
        metadata: dict | None = None,
    ) -> LangfuseTurn:
        """Create a child *turn* span for this user message."""
        return LangfuseTurn.start(
            parent=self._trace,
            name=name,
            input=input,
            metadata=metadata,
        )

    # ── lifecycle ────────────────────────────────────────────────────
    def update(self, **kwargs: Any) -> None:
        if self._trace:
            try:
                self._trace.update(**kwargs)
            except Exception as e:
                log.debug('Langfuse trace update failed: %s', e)


# ──────────────────────────────────────────────────────────────────────
# Turn  –  one user-message → response cycle
# ──────────────────────────────────────────────────────────────────────
class LangfuseTurn:
    """Exception-safe wrapper representing one conversational turn.

    A turn contains:
    - One or more LLM generation (the model calls, including retries)
    - Zero or more tool call spans
    """

    __slots__ = ('_span', '_round_counter')

    def __init__(self):
        self._span = None
        self._round_counter = 0

    @property
    def enabled(self) -> bool:
        return self._span is not None

    @classmethod
    def start(
        cls,
        *,
        parent: Any,
        name: str,
        input: Any = None,
        metadata: dict | None = None,
    ) -> LangfuseTurn:
        obj = cls()
        if parent is None:
            return obj
        try:
            obj._span = parent.span(
                name=name,
                input=input,
                metadata=metadata or {},
            )
        except Exception as e:
            log.debug('Langfuse turn create failed: %s', e)
        return obj

    def generation(
        self,
        *,
        model: str = '',
        input: Any = None,
        metadata: dict | None = None,
        model_parameters: dict | None = None,
    ) -> LangfuseGeneration:
        """Create an LLM *generation* nested under this turn."""
        self._round_counter += 1
        name = f'llm_call' if self._round_counter == 1 else f'llm_call_{self._round_counter}'
        return LangfuseGeneration.start(
            parent=self._span,
            name=name,
            model=model,
            input=input,
            metadata=metadata,
            model_parameters=model_parameters,
        )

    def tool_span(
        self,
        *,
        name: str,
        input: Any = None,
        metadata: dict | None = None,
    ) -> LangfuseSpan:
        """Create a tool call *span* nested under this turn."""
        return LangfuseSpan.start(
            parent=self._span,
            name=name,
            input=input,
            metadata=metadata,
        )

    def end(self, *, output: Any = None, metadata: dict | None = None) -> None:
        if self._span:
            try:
                kw: dict[str, Any] = {}
                if output is not None:
                    kw['output'] = output
                if metadata:
                    kw['metadata'] = metadata
                self._span.end(**kw)
            except Exception as e:
                log.debug('Langfuse turn end failed: %s', e)


# ──────────────────────────────────────────────────────────────────────
# Generation  –  one LLM invocation
# ──────────────────────────────────────────────────────────────────────
class LangfuseGeneration:
    """Exception-safe wrapper around a Langfuse *generation*."""

    __slots__ = ('_gen',)

    def __init__(self):
        self._gen = None

    @property
    def enabled(self) -> bool:
        return self._gen is not None

    @classmethod
    def start(
        cls,
        *,
        parent: Any,
        name: str,
        model: str = '',
        input: Any = None,
        metadata: dict | None = None,
        model_parameters: dict | None = None,
    ) -> LangfuseGeneration:
        obj = cls()
        if parent is None:
            return obj
        try:
            obj._gen = parent.generation(
                name=name,
                model=model,
                input=input,
                metadata=metadata or {},
                model_parameters=model_parameters or {},
            )
        except Exception as e:
            log.debug('Langfuse generation create failed: %s', e)
        return obj

    def update(self, **kwargs: Any) -> None:
        if self._gen:
            try:
                self._gen.update(**kwargs)
            except Exception as e:
                log.debug('Langfuse generation update failed: %s', e)

    def end(
        self,
        *,
        output: Any = None,
        usage: dict | None = None,
        metadata: dict | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> None:
        if self._gen:
            try:
                kw: dict[str, Any] = {}
                if output is not None:
                    kw['output'] = output
                if usage:
                    kw['usage'] = usage
                if metadata:
                    kw['metadata'] = metadata
                if level:
                    kw['level'] = level
                if status_message:
                    kw['status_message'] = status_message
                self._gen.end(**kw)
            except Exception as e:
                log.debug('Langfuse generation end failed: %s', e)


# ──────────────────────────────────────────────────────────────────────
# Span  –  tool call, reasoning block, etc.
# ──────────────────────────────────────────────────────────────────────
class LangfuseSpan:
    """Exception-safe wrapper around a Langfuse *span*."""

    __slots__ = ('_span',)

    def __init__(self):
        self._span = None

    @property
    def enabled(self) -> bool:
        return self._span is not None

    @classmethod
    def start(
        cls,
        *,
        parent: Any,
        name: str,
        input: Any = None,
        metadata: dict | None = None,
    ) -> LangfuseSpan:
        obj = cls()
        if parent is None:
            return obj
        try:
            obj._span = parent.span(
                name=name,
                input=input,
                metadata=metadata or {},
            )
        except Exception as e:
            log.debug('Langfuse span create failed: %s', e)
        return obj

    def end(
        self,
        *,
        output: Any = None,
        metadata: dict | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> None:
        if self._span:
            try:
                kw: dict[str, Any] = {}
                if output is not None:
                    kw['output'] = output
                if metadata:
                    kw['metadata'] = metadata
                if level:
                    kw['level'] = level
                if status_message:
                    kw['status_message'] = status_message
                self._span.end(**kw)
            except Exception as e:
                log.debug('Langfuse span end failed: %s', e)


# ──────────────────────────────────────────────────────────────────────
# Module-level helpers
# ──────────────────────────────────────────────────────────────────────
def flush() -> None:
    """Flush pending events.  Call on graceful shutdown."""
    if _langfuse_client:
        try:
            _langfuse_client.flush()
        except Exception as e:
            log.debug('Langfuse flush failed: %s', e)


def shutdown() -> None:
    """Shutdown the client.  Call on process exit."""
    global _langfuse_client
    if _langfuse_client:
        try:
            _langfuse_client.shutdown()
        except Exception as e:
            log.debug('Langfuse shutdown failed: %s', e)
        _langfuse_client = None
