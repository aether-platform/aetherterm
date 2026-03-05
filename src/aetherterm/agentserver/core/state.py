"""Observable state management for AetherTerm.

Provides classes to track state changes and notify observers,
facilitating clearer state transitions and synchronization.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Observable(Generic[T]):
    """Wrapper for a value that notifies observers on change."""

    def __init__(self, value: T, name: str = ""):
        self._value = value
        self._name = name
        self._observers: List[Callable[[T, T], None]] = []

    @property
    def value(self) -> T:
        return self._value

    @value.setter
    def value(self, new_value: T):
        if self._value != new_value:
            old_value = self._value
            self._value = new_value
            self._notify(old_value, new_value)

    def subscribe(self, observer: Callable[[T, T], None]):
        """Subscribe to changes (callback: (old, new) -> None)."""
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer: Callable[[T, T], None]):
        """Unsubscribe from changes."""
        if observer in self._observers:
            self._observers.append(observer)

    def _notify(self, old_value: T, new_value: T):
        for observer in self._observers:
            try:
                if asyncio.iscoroutinefunction(observer):
                    asyncio.create_task(observer(old_value, new_value))
                else:
                    observer(old_value, new_value)
            except Exception as e:
                logger.error(f"Error in observer '{self._name}': {e}")


class StateBase:
    """Base class for observable states."""

    def __init__(self):
        self._sync_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None

    def set_sync_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Callback to sync state with frontend: (id, data) -> None."""
        self._sync_callback = callback

    def _on_change(self, name: str, old: Any, new: Any):
        if self._sync_callback:
            # We trigger a full or partial sync here
            self._sync_callback(getattr(self, "id", "unknown"), self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to serializable dictionary."""
        result = {}
        for name, value in self.__dict__.items():
            if isinstance(value, Observable):
                result[name.lstrip("_")] = value.value
            elif not name.startswith("_"):
                result[name] = value
        return result


class PaneState(StateBase):
    """Observable state for a single Pane."""

    def __init__(self, pane_id: str, mode: str = "terminal"):
        super().__init__()
        self.id = pane_id
        self._mode = Observable(mode, f"pane_{pane_id}_mode")
        self._is_locked = Observable(False, f"pane_{pane_id}_locked")
        self._title = Observable("Terminal", f"pane_{pane_id}_title")

        # Internal subscription to trigger sync
        self._mode.subscribe(lambda o, n: self._on_change("mode", o, n))
        self._is_locked.subscribe(lambda o, n: self._on_change("is_locked", o, n))
        self._title.subscribe(lambda o, n: self._on_change("title", o, n))

    @property
    def mode(self) -> str:
        return self._mode.value

    @mode.setter
    def mode(self, val: str):
        self._mode.value = val

    @property
    def is_locked(self) -> bool:
        return self._is_locked.value

    @is_locked.setter
    def is_locked(self, val: bool):
        self._is_locked.value = val

    @property
    def title(self) -> str:
        return self._title.value

    @title.setter
    def title(self, val: str):
        self._title.value = val


class SessionState(StateBase):
    """Observable state for a Session."""

    def __init__(self, session_id: str):
        super().__init__()
        self.id = session_id
        self._active_pane_id = Observable("", f"session_{session_id}_active_pane")
        self._is_ready = Observable(False, f"session_{session_id}_ready")
        self.panes: Dict[str, PaneState] = {}

        self._active_pane_id.subscribe(lambda o, n: self._on_change("active_pane_id", o, n))
        self._is_ready.subscribe(lambda o, n: self._on_change("is_ready", o, n))

    @property
    def active_pane_id(self) -> str:
        return self._active_pane_id.value

    @active_pane_id.setter
    def active_pane_id(self, val: str):
        self._active_pane_id.value = val

    @property
    def is_ready(self) -> bool:
        return self._is_ready.value

    @is_ready.setter
    def is_ready(self, val: bool):
        self._is_ready.value = val

    def add_pane(self, pane_state: PaneState):
        self.panes[pane_state.id] = pane_state
        # Forward pane sync to session sync
        if self._sync_callback:
            pane_state.set_sync_callback(lambda i, d: self._on_change(f"pane_{i}", None, d))

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["panes"] = {k: v.to_dict() for k, v in self.panes.items()}
        return d
