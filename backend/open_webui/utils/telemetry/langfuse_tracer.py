"""
Langfuse LLM observability integration for Open WebUI.

This implementation sends events directly to Langfuse's public ingestion API
instead of relying on the Python SDK. The SDK can emit payloads that are not
compatible with this self-hosted Langfuse server version, while the public
`/api/public/ingestion` API has been verified to work for this deployment.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from open_webui.env import (
    ENABLE_LANGFUSE,
    LANGFUSE_SECRET_KEY,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_HOST,
    GLOBAL_LOG_LEVEL,
)

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)

_langfuse_client = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in d.items() if v is not None}


class _IngestionClient:
    def __init__(self, *, public_key: str, secret_key: str, host: str):
        self.host = host.rstrip('/')
        self.endpoint = f'{self.host}/api/public/ingestion'
        token = base64.b64encode(f'{public_key}:{secret_key}'.encode()).decode()
        self.headers = {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
        }
        self._batch: list[dict[str, Any]] = []

    def emit(self, event_type: str, body: dict[str, Any]) -> None:
        self._batch.append(
            {
                'id': str(uuid4()),
                'timestamp': _now(),
                'type': event_type,
                'body': _clean(body),
            }
        )

    def flush(self) -> None:
        if not self._batch:
            return
        batch = self._batch
        self._batch = []
        payload = {'batch': batch}
        try:
            import httpx

            resp = httpx.post(
                self.endpoint,
                headers=self.headers,
                content=json.dumps(payload, ensure_ascii=False, default=str),
                timeout=20,
            )
            if resp.status_code < 200 or resp.status_code >= 300:
                log.error(
                    'Langfuse ingestion failed: status=%s body=%s',
                    resp.status_code,
                    resp.text[:1000],
                )
            else:
                log.debug('Langfuse ingestion flushed %s event(s)', len(batch))
        except Exception as e:
            log.error('Langfuse ingestion request failed: %s', e)

    def shutdown(self) -> None:
        self.flush()


def get_langfuse():
    global _langfuse_client
    if not ENABLE_LANGFUSE:
        return None
    if _langfuse_client is None:
        try:
            _langfuse_client = _IngestionClient(
                secret_key=LANGFUSE_SECRET_KEY,
                public_key=LANGFUSE_PUBLIC_KEY,
                host=LANGFUSE_HOST,
            )
            log.info('Langfuse ingestion client initialised (host=%s)', LANGFUSE_HOST)
        except Exception as e:
            log.error('Failed to initialise Langfuse ingestion client: %s', e)
    return _langfuse_client


class LangfuseTrace:
    __slots__ = ('_trace',)

    def __init__(self):
        self._trace = None

    @property
    def enabled(self) -> bool:
        return self._trace is not None

    @classmethod
    def start(
        cls,
        *,
        trace_id: str,
        name: str = 'chat_session',
        user_id: str | None = None,
        session_id: str | None = None,
        input: Any = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> 'LangfuseTrace':
        obj = cls()
        client = get_langfuse()
        if client is None:
            return obj
        try:
            trace_id = trace_id or str(uuid4())
            client.emit(
                'trace-create',
                {
                    'id': trace_id,
                    'timestamp': _now(),
                    'name': name,
                    'userId': user_id,
                    'sessionId': session_id,
                    'input': input,
                    'metadata': metadata or {},
                    'tags': tags or [],
                },
            )
            obj._trace = {'id': trace_id, 'client': client}
        except Exception as e:
            log.warning('Failed to create/get Langfuse trace: %s', e)
        return obj

    def turn(
        self,
        *,
        name: str = 'turn',
        input: Any = None,
        metadata: dict | None = None,
    ) -> 'LangfuseTurn':
        return LangfuseTurn.start(
            parent=self._trace,
            name=name,
            input=input,
            metadata=metadata,
        )

    def update(self, **kwargs: Any) -> None:
        if self._trace:
            try:
                self._trace['client'].emit(
                    'trace-create',
                    {'id': self._trace['id'], 'timestamp': _now(), **kwargs},
                )
            except Exception as e:
                log.debug('Langfuse trace update failed: %s', e)


class LangfuseTurn:
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
    ) -> 'LangfuseTurn':
        obj = cls()
        if parent is None:
            return obj
        try:
            span_id = str(uuid4())
            parent['client'].emit(
                'span-create',
                {
                    'id': span_id,
                    'traceId': parent['id'],
                    'name': name,
                    'startTime': _now(),
                    'input': input,
                    'metadata': metadata or {},
                },
            )
            obj._span = {'id': span_id, 'trace_id': parent['id'], 'client': parent['client']}
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
    ) -> 'LangfuseGeneration':
        self._round_counter += 1
        name = 'llm_call' if self._round_counter == 1 else f'llm_call_{self._round_counter}'
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
    ) -> 'LangfuseSpan':
        return LangfuseSpan.start(
            parent=self._span,
            name=name,
            input=input,
            metadata=metadata,
        )

    def end(self, *, output: Any = None, metadata: dict | None = None) -> None:
        if self._span:
            try:
                self._span['client'].emit(
                    'span-update',
                    {
                        'id': self._span['id'],
                        'traceId': self._span['trace_id'],
                        'endTime': _now(),
                        'output': output,
                        'metadata': metadata,
                    },
                )
            except Exception as e:
                log.debug('Langfuse turn end failed: %s', e)


class LangfuseGeneration:
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
    ) -> 'LangfuseGeneration':
        obj = cls()
        if parent is None:
            return obj
        try:
            gen_id = str(uuid4())
            parent['client'].emit(
                'generation-create',
                {
                    'id': gen_id,
                    'traceId': parent['trace_id'],
                    'parentObservationId': parent['id'],
                    'name': name,
                    'startTime': _now(),
                    'model': model,
                    'input': input,
                    'metadata': metadata or {},
                    'modelParameters': model_parameters or {},
                },
            )
            obj._gen = {'id': gen_id, 'trace_id': parent['trace_id'], 'client': parent['client']}
        except Exception as e:
            log.debug('Langfuse generation create failed: %s', e)
        return obj

    def update(self, **kwargs: Any) -> None:
        if self._gen:
            try:
                self._gen['client'].emit(
                    'generation-update',
                    {'id': self._gen['id'], 'traceId': self._gen['trace_id'], **kwargs},
                )
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
                self._gen['client'].emit(
                    'generation-update',
                    {
                        'id': self._gen['id'],
                        'traceId': self._gen['trace_id'],
                        'endTime': _now(),
                        'output': output,
                        'usage': usage,
                        'metadata': metadata,
                        'level': level,
                        'statusMessage': status_message,
                    },
                )
            except Exception as e:
                log.debug('Langfuse generation end failed: %s', e)


class LangfuseSpan:
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
    ) -> 'LangfuseSpan':
        obj = cls()
        if parent is None:
            return obj
        try:
            span_id = str(uuid4())
            parent['client'].emit(
                'span-create',
                {
                    'id': span_id,
                    'traceId': parent['trace_id'],
                    'parentObservationId': parent['id'],
                    'name': name,
                    'startTime': _now(),
                    'input': input,
                    'metadata': metadata or {},
                },
            )
            obj._span = {'id': span_id, 'trace_id': parent['trace_id'], 'client': parent['client']}
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
                self._span['client'].emit(
                    'span-update',
                    {
                        'id': self._span['id'],
                        'traceId': self._span['trace_id'],
                        'endTime': _now(),
                        'output': output,
                        'metadata': metadata,
                        'level': level,
                        'statusMessage': status_message,
                    },
                )
            except Exception as e:
                log.debug('Langfuse span end failed: %s', e)


def flush() -> None:
    if _langfuse_client:
        try:
            _langfuse_client.flush()
        except Exception as e:
            log.debug('Langfuse flush failed: %s', e)


def shutdown() -> None:
    global _langfuse_client
    if _langfuse_client:
        try:
            _langfuse_client.shutdown()
        except Exception as e:
            log.debug('Langfuse shutdown failed: %s', e)
        _langfuse_client = None
