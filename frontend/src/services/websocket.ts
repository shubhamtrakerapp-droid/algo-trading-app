export type ConnectionState = 'CONNECTED' | 'CONNECTING' | 'DISCONNECTED' | 'RECONNECTING' | 'STALE DATA' | 'MARKET CLOSED';

export type MessageListener = (data: any) => void;
export type StatusListener = (status: ConnectionState, details?: any) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private listeners: Set<MessageListener> = new Set();
  private statusListeners: Set<StatusListener> = new Set();
  private reconnectTimeout: number | null = null;
  private pingInterval: number | null = null;
  private staleTimer: number | null = null;

  public isConnected: boolean = false;
  public connectionState: ConnectionState = 'DISCONNECTED';
  public lastTickTime: Date | null = null;
  public lastMessageTime: Date | null = null;
  public activeSubscriptions: Set<string> = new Set(['NIFTY 50', 'NIFTY ATM CE']);
  private reconnectAttempts: number = 0;

  public connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.setConnectionState(this.reconnectAttempts > 0 ? 'RECONNECTING' : 'CONNECTING');

    const envWsUrl = import.meta.env.VITE_WS_URL;
    let wsUrl = envWsUrl;
    if (!wsUrl) {
      const backendBase = import.meta.env.VITE_API_BASE_URL;
      if (backendBase) {
        const wsProto = backendBase.startsWith('https://') ? 'wss://' : 'ws://';
        const wsHost = backendBase.replace(/^https?:\/\//, '').replace(/\/.*$/, '');
        wsUrl = `${wsProto}${wsHost}/ws`;
      } else {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        wsUrl = `${protocol}//${host}/ws`;
      }
    }

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.setConnectionState('CONNECTED');
        this.startPing();
        this.startStaleMonitor();

        // Automatically resubscribe to all active symbols on connection
        if (this.activeSubscriptions.size > 0) {
          this.send({
            type: 'SUBSCRIBE',
            symbols: Array.from(this.activeSubscriptions),
          });
        }

        this.notify({ type: 'WS_CONNECTED', data: { isConnected: true } });
      };

      this.ws.onmessage = (event) => {
        this.lastMessageTime = new Date();
        try {
          if (event.data === 'pong') return;
          const msg = JSON.parse(event.data);

          if (msg.type === 'INITIAL_SNAPSHOT') {
            if (msg.data?.connection_state === 'MARKET CLOSED') {
              this.setConnectionState('MARKET CLOSED');
            } else if (msg.data?.connection_state === 'CONNECTED') {
              this.setConnectionState('CONNECTED');
            }
          } else if (msg.type === 'TICK' || msg.type === 'FORMING_CANDLE' || msg.type === 'OPTION_CHAIN_TICK' || msg.type === 'OPTION_CHAIN_SPOT') {
            this.lastTickTime = new Date();
            if (this.connectionState === 'STALE DATA') {
              this.setConnectionState('CONNECTED');
            }
          } else if (msg.type === 'FEED_STATUS') {
            const rawStatus = msg.data?.status;
            if (rawStatus === 'MARKET CLOSED') {
              this.setConnectionState('MARKET CLOSED');
            } else if (rawStatus === 'CONNECTED' || rawStatus === 'DEMO_CONNECTED') {
              this.setConnectionState('CONNECTED');
            } else if (rawStatus === 'DISCONNECTED') {
              this.setConnectionState('DISCONNECTED');
            }
          }

          this.notify(msg);
        } catch (e) {
          // ignore non-json
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.stopPing();
        this.stopStaleMonitor();
        this.setConnectionState('DISCONNECTED');
        this.notify({ type: 'WS_DISCONNECTED', data: { isConnected: false } });
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.isConnected = false;
        this.ws?.close();
      };
    } catch {
      this.scheduleReconnect();
    }
  }

  public send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }

  public subscribeSymbols(symbols: string[]) {
    if (!symbols || symbols.length === 0) return;
    symbols.forEach((s) => this.activeSubscriptions.add(s));
    this.send({
      type: 'SUBSCRIBE',
      symbols,
    });
  }

  public unsubscribeSymbols(symbols: string[]) {
    if (!symbols || symbols.length === 0) return;
    symbols.forEach((s) => this.activeSubscriptions.delete(s));
    this.send({
      type: 'UNSUBSCRIBE',
      symbols,
    });
  }

  private setConnectionState(state: ConnectionState) {
    this.connectionState = state;
    for (const listener of this.statusListeners) {
      try {
        listener(state);
      } catch (e) {
        console.error('Error in status listener:', e);
      }
    }
  }

  public onStatusChange(listener: StatusListener) {
    this.statusListeners.add(listener);
    listener(this.connectionState);
    return () => {
      this.statusListeners.delete(listener);
    };
  }

  public getConnectionHealth() {
    const now = new Date().getTime();
    const dataAgeSeconds = this.lastTickTime
      ? Math.max(0, Math.round((now - this.lastTickTime.getTime()) / 100) / 10)
      : null;

    return {
      state: this.connectionState,
      isConnected: this.isConnected,
      lastTickTime: this.lastTickTime,
      dataAgeSeconds,
      subscriptionsCount: this.activeSubscriptions.size,
    };
  }

  private startPing() {
    this.stopPing();
    this.pingInterval = window.setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 10000);
  }

  private stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private startStaleMonitor() {
    this.stopStaleMonitor();
    this.staleTimer = window.setInterval(() => {
      if (this.isConnected && this.lastTickTime && this.connectionState === 'CONNECTED') {
        const elapsed = (Date.now() - this.lastTickTime.getTime()) / 1000;
        if (elapsed > 15) {
          this.setConnectionState('STALE DATA');
        }
      }
    }, 2000);
  }

  private stopStaleMonitor() {
    if (this.staleTimer) {
      clearInterval(this.staleTimer);
      this.staleTimer = null;
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimeout) return;
    this.reconnectAttempts += 1;
    this.setConnectionState('RECONNECTING');

    // Exponential backoff: 1s, 1.5s, 2.2s ... up to 10s max
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts - 1), 10000);

    this.reconnectTimeout = window.setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect();
    }, delay);
  }

  public subscribe(listener: MessageListener) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(message: any) {
    for (const listener of this.listeners) {
      try {
        listener(message);
      } catch (e) {
        console.error('Error in WS listener:', e);
      }
    }
  }
}

export const wsClient = new WebSocketClient();
