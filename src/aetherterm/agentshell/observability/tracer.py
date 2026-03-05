"""分散トレーシング機能

OpenTelemetryを使用した分散トレーシングの実装と、
AetherTermシェル操作のトレース記録を提供します。
"""

import functools
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional, TypeVar, Union

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from .logger import LoggerFactory

# 型ヒント用
F = TypeVar("F", bound=Callable[..., Any])

logger = LoggerFactory.create_telemetry_logger()


class DistributedTracer:
    """分散トレーシングクラス

    OpenTelemetryトレーサーのラッパーとして機能し、
    AetherTermシェル操作の詳細なトレーシングを提供します。
    """

    def __init__(self, service_name: str = "aetherterm-shell"):
        self.service_name = service_name
        self._tracer = trace.get_tracer(service_name)

    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None,
        kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    ) -> trace.Span:
        """新しいスパンを開始"""
        span = self._tracer.start_span(
            name=name,
            kind=kind,
            attributes=attributes or {},
        )
        return span

    @contextmanager
    def trace_operation(
        self,
        operation_name: str,
        attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None,
        record_exception: bool = True,
    ):
        """操作をトレースするコンテキストマネージャー"""
        with self._tracer.start_as_current_span(
            operation_name,
            attributes=attributes or {},
        ) as span:
            start_time = time.time()
            try:
                yield span
                # 成功時の情報を記録
                duration = time.time() - start_time
                span.set_attribute("operation.duration", duration)
                span.set_status(Status(StatusCode.OK))

            except Exception as e:
                # エラー時の情報を記録
                duration = time.time() - start_time
                span.set_attribute("operation.duration", duration)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))

                if record_exception:
                    span.record_exception(e)

                logger.error(f"Operation failed: {operation_name}", error=e)
                raise

    def trace_session_operation(self, operation_name: str, session_id: str, **attributes):
        """セッション操作をトレースするコンテキストマネージャー"""
        attrs = {"session.id": session_id, "operation.type": "session", **attributes}
        return self.trace_operation(f"session.{operation_name}", attrs)

    def trace_command_execution(self, command: str, session_id: str, **attributes):
        """コマンド実行をトレースするコンテキストマネージャー"""
        attrs = {
            "command.name": command.split()[0] if command.split() else command,
            "command.full": command,
            "session.id": session_id,
            "operation.type": "command",
            **attributes,
        }
        return self.trace_operation("command.execute", attrs)

    def trace_ai_interaction(
        self, interaction_type: str, model: Optional[str] = None, **attributes
    ):
        """AI連携をトレースするコンテキストマネージャー"""
        attrs = {"ai.interaction_type": interaction_type, "operation.type": "ai", **attributes}
        if model:
            attrs["ai.model"] = model
        return self.trace_operation(f"ai.{interaction_type}", attrs)

    def trace_file_operation(self, operation: str, file_path: str, **attributes):
        """ファイル操作をトレースするコンテキストマネージャー"""
        attrs = {
            "file.path": file_path,
            "file.operation": operation,
            "operation.type": "file",
            **attributes,
        }
        return self.trace_operation(f"file.{operation}", attrs)

    def trace_network_operation(
        self, operation: str, endpoint: str, method: Optional[str] = None, **attributes
    ):
        """ネットワーク操作をトレースするコンテキストマネージャー"""
        attrs = {
            "network.endpoint": endpoint,
            "network.operation": operation,
            "operation.type": "network",
            **attributes,
        }
        if method:
            attrs["http.method"] = method
        return self.trace_operation(f"network.{operation}", attrs)

    def add_event(
        self,
        name: str,
        attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None,
        timestamp: Optional[int] = None,
    ) -> None:
        """現在のスパンにイベントを追加"""
        span = trace.get_current_span()
        if span and span.is_recording():
            span.add_event(name, attributes or {}, timestamp)

    def set_attribute(
        self,
        key: str,
        value: Union[str, int, float, bool],
    ) -> None:
        """現在のスパンに属性を設定"""
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(key, value)

    def set_status(
        self,
        status_code: StatusCode,
        description: Optional[str] = None,
    ) -> None:
        """現在のスパンのステータスを設定"""
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_status(Status(status_code, description))

    def record_exception(
        self,
        exception: Exception,
        attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None,
    ) -> None:
        """現在のスパンに例外を記録"""
        span = trace.get_current_span()
        if span and span.is_recording():
            span.record_exception(exception, attributes)


def trace_method(
    operation_name: Optional[str] = None,
    attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None,
    record_exception: bool = True,
) -> Callable[[F], F]:
    """メソッドをトレースするデコレーター

    Args:
        operation_name: 操作名（指定しない場合はメソッド名を使用）
        attributes: 追加属性
        record_exception: 例外を記録するかどうか

    Returns:
        デコレートされた関数
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = DistributedTracer()
            op_name = operation_name or f"{func.__module__}.{func.__qualname__}"

            attrs = {
                "function.name": func.__name__,
                "function.module": func.__module__,
                **(attributes or {}),
            }

            with tracer.trace_operation(op_name, attrs, record_exception):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def trace_async_method(
    operation_name: Optional[str] = None,
    attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None,
    record_exception: bool = True,
) -> Callable[[F], F]:
    """非同期メソッドをトレースするデコレーター

    Args:
        operation_name: 操作名（指定しない場合はメソッド名を使用）
        attributes: 追加属性
        record_exception: 例外を記録するかどうか

    Returns:
        デコレートされた非同期関数
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = DistributedTracer()
            op_name = operation_name or f"{func.__module__}.{func.__qualname__}"

            attrs = {
                "function.name": func.__name__,
                "function.module": func.__module__,
                "function.async": True,
                **(attributes or {}),
            }

            with tracer.trace_operation(op_name, attrs, record_exception):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


class TracingContext:
    """トレーシングコンテキスト管理

    複数の操作にわたってトレーシング情報を共有するための
    コンテキスト管理クラスです。
    """

    def __init__(self, tracer: DistributedTracer):
        self.tracer = tracer
        self._context_attributes: Dict[str, Union[str, int, float, bool]] = {}

    def set_context_attribute(
        self,
        key: str,
        value: Union[str, int, float, bool],
    ) -> None:
        """コンテキスト属性を設定"""
        self._context_attributes[key] = value

    def get_context_attributes(self) -> Dict[str, Union[str, int, float, bool]]:
        """コンテキスト属性を取得"""
        return self._context_attributes.copy()

    def trace_with_context(
        self,
        operation_name: str,
        additional_attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None,
    ):
        """コンテキスト属性を含めて操作をトレース"""
        attrs = self._context_attributes.copy()
        if additional_attributes:
            attrs.update(additional_attributes)

        return self.tracer.trace_operation(operation_name, attrs)


# グローバルトレーサーインスタンス
_global_tracer: Optional[DistributedTracer] = None


def get_tracer() -> DistributedTracer:
    """グローバルトレーサーを取得"""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = DistributedTracer()
    return _global_tracer


def set_tracer(tracer: DistributedTracer) -> None:
    """グローバルトレーサーを設定"""
    global _global_tracer
    _global_tracer = tracer
