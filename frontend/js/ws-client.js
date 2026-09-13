/**
 * Minimal Socket.IO-style wrapper around the browser's native WebSocket,
 * talking to the FastAPI backend's single /ws endpoint. Messages are JSON:
 * { type: "<event>", payload: {...} } in both directions.
 */
function createSocket() {
  const listeners = {};
  let ws = null;
  let closedByUs = false;
  let reconnectDelay = 1000;

  function on(type, cb) {
    (listeners[type] = listeners[type] || []).push(cb);
  }

  function emit(type, payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, payload: payload || {} }));
    }
  }

  function fire(type, payload) {
    (listeners[type] || []).forEach((cb) => { try { cb(payload); } catch (e) { console.error(e); } });
  }

  function connect() {
    const token = Api.getToken();
    if (!token) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws?token=${encodeURIComponent(token)}`);

    ws.onopen = () => { reconnectDelay = 1000; fire('connect', {}); };
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        fire(msg.type, msg.payload);
      } catch (_) { /* ignore malformed frame */ }
    };
    ws.onclose = () => {
      fire('disconnect', {});
      if (!closedByUs) {
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 1.6, 15000);
      }
    };
    ws.onerror = () => { try { ws.close(); } catch (_) {} };
  }

  connect();

  return { on, emit, close: () => { closedByUs = true; if (ws) ws.close(); } };
}
