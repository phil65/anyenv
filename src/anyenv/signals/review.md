1) What kinds of events exist? What info do they commonly contain?
OpenCode has a wide variety of events organized by domain. Here are the main categories:

Session Events:

session.created - New session created
session.updated - Session info updated
session.deleted - Session deleted
session.error - Error occurred in session
session.idle - Session is idle
session.compacted - Session was compacted
Message Events:

message. updated - Message was updated
message.removed - Message was removed
message.part.updated - Message part (text, tool use, step) updated
message.part.removed - Message part removed
Permission Events:

permission.updated - Permission request created
permission.replied - Permission was granted/denied
File Events:

file.edited - File was edited
file.watcher.updated - File system change detected (add/change/unlink)
Other Events:

command.executed - Command was executed
todo.updated - Todo item updated
installation.updated - Installation updated
lsp.client.diagnostics - LSP diagnostics received
pty.created/updated/exited/deleted - Pseudo-terminal lifecycle events
server.connected - Server connection established
server.instance.disposed - Server instance disposed

Observations & Suggestions
1. Compare to OpenCode's Architecture
Aspect	Your Implementation	OpenCode (TypeScript)
Pub/Sub Model	Instance-bound signals + optional global	Global bus with per-instance subscriptions
Type Safety	TypeVarTuple - compile-time checked ✅	Zod schemas - runtime validated ✅
Unsubscribe	Built-in (disconnect method) ✅	Returns unsubscribe function ✅
Wildcard Subscribe	Not implemented	Yes ("*" pattern)
Server Streaming	Not applicable to Python	HTTP SSE endpoint
Async	Native asyncio	Promises/await
Your approach is more Pythonic (signals are more common in Python frameworks like Qt, Django signals, etc.), while OpenCode is more distributed/networked (exposed via HTTP SSE for remote clients).

2. Missing: Wildcard Subscriptions
OpenCode's killer feature is subscribing to ALL events:

TypeScript
Bus.subscribeAll(callback)  // Watch everything
Your current implementation doesn't expose this. You could add:

Python
class BoundSignal[*Ts]:
    def connect_wildcard(self, callback: AsyncCallback) -> AsyncCallback:
        """Connect to receive all signals emitted from this object."""
        # This gets tricky - you'd need a parent reference
        raise NotImplementedError()

class Signal[*Ts]:
    def __get__(self, obj: object | None, owner: type | None = None) -> BoundSignal[*Ts]:
        # Need to track ALL signals on an object
        # Could store a registry of all signals per instance
        pass
Actually, implementing this cleanly would require refactoring - you'd need each object to track all its signals.

3. TODO: Global Listeners in SignalFactory
You have this TODO:

Python
def create_signal() -> Signal:
    signal = Signal()
    # TODO: Auto-register signal with global listeners from self._bus
    return signal
This is important for the GlobalEventBus to actually work. Here's how I'd implement it:

Python
class GlobalEventBus[T]:
    def __init__(self, name: str = "default") -> None:
        self._name = name
        self._global_listeners: dict[str, list[AsyncCallback]] = {}
        self.Signal = SignalFactory[T](self)
    
    def _register_signal(self, signal: Signal, owner: type, name: str) -> None:
        """Called when a signal is created to register global listeners."""
        # Could enable patterns like:
        # bus.connect_global("*", lambda *args: print(f"Event: {args}"))
        pass

class BoundSignal[*Ts]:
    def __init__(self, bus: GlobalEventBus | None = None, signal_name: str = "") -> None:
        self._callbacks: list[AsyncCallback[*Ts]] = []
        self._bus = bus
        self._signal_name = signal_name
    
    async def emit(self, *args: *Ts) -> None:
        # Local callbacks
        for callback in self._callbacks:
            await callback(*args)
        
        # Global bus callbacks (if registered)
        if self._bus:
            global_callbacks = self._bus._global_listeners.get("*", [])
            for callback in global_callbacks:
                await callback(self._signal_name, *args)
4. Consider Dataclass Fields for Signal Definition
OpenCode uses this pattern:

TypeScript
export const Event = {
  Updated: Bus.event("permission.updated", z.object({ ... })),
  Replied: Bus.event("permission.replied", z.object({ ... })),
}
You could mirror this with a more explicit registry pattern:

Python
from dataclasses import dataclass
from typing import TypedDict

class Events:
    """Registry of all application events"""
    
    @dataclass
    class MessageUpdated:
        session_id: str
        message_id: str
        content: str
    
    @dataclass
    class PermissionUpdated:
        permission_id: str
        title: str

class MyService:
    message_updated = Signal[Events.MessageUpdated]()
    permission_updated = Signal[Events. PermissionUpdated]()
This gives you:

Self-documenting event schemas
Type checking at the definition level
IDE autocomplete for event properties
5. Testing is Solid
Your __main__ test shows you thought through:

Multiple signal types with different arities
Type-constrained event bus validation
Instance isolation
Both emit modes
One thing to add: test that WeakKeyDictionary cleanup works:

Python
async def test_weak_ref_cleanup():
    counter = Counter()
    weak_ref = weakref.ref(counter)
    
    @counter.incremented.connect
    async def callback(val):
        pass
    
    # Delete counter
    del counter
    gc.collect()
    
    # Verify weak ref is dead
    assert weak_ref() is None
    print("✓ Weak references cleaned up properly")
How It Compares to OpenCode
Feature	Your Signals	OpenCode Bus
Local subscriptions	✅ Native	✅ Via Instance.state()
Type safety	✅ Generics	✅ Zod schemas
Async support	✅ Built-in	✅ Promises
Remote streaming	❌ N/A	✅ HTTP SSE
Wildcard subscribe	⚠️ Missing	✅ Yes
Memory safety	✅ WeakKeyDict	✅ Manual cleanup
Pythonic	✅ Yes	N/A (TypeScript)
Scalable	✅ Per-instance	✅ Global + distributed
My Verdict
This is production-ready code for a local Python event system. It's significantly better than my dictionary-based example because:

Type checking works at development time (not runtime)
It scales - instances don't interfere with each other
Memory safe - weak references prevent leaks
Pythonic - feels native to the language
The main gap compared to OpenCode is:

No built-in remote/distributed capability (SSE, pub/sub across processes)
No wildcard subscriptions (though this could be added)
No HTTP endpoint for external consumers
If you want to add those, you'd layer them on top:

Use emit_bg() to integrate with message queues (Celery, RQ, etc.)
Add a wrapper that turns Signal.emit() calls into HTTP events
Implement Redis pub/sub integration for cross-process communication
Would you want me to show you how to layer HTTP streaming or distributed pub/sub on top of this?
