type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  data?: any;
  stack?: string;
}

class Logger {
  private logs: LogEntry[] = [];
  private maxLogs = 1000;
  private isDevelopment = import.meta.env.MODE === 'development';

  private formatMessage(level: LogLevel, message: string): string {
    const timestamp = new Date().toISOString();
    const emoji = {
      debug: '🔍',
      info: 'ℹ️',
      warn: '⚠️',
      error: '❌'
    }[level];
    
    return `${emoji} [${timestamp}] ${level.toUpperCase()}: ${message}`;
  }

  private addToHistory(entry: LogEntry) {
    this.logs.push(entry);
    if (this.logs.length > this.maxLogs) {
      this.logs.shift();
    }
  }

  debug(message: string, data?: any) {
    if (!this.isDevelopment) return;
    
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'debug',
      message,
      data
    };
    
    this.addToHistory(entry);
    console.log(this.formatMessage('debug', message), data || '');
  }

  info(message: string, data?: any) {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'info',
      message,
      data
    };
    
    this.addToHistory(entry);
    console.info(this.formatMessage('info', message), data || '');
  }

  warn(message: string, data?: any) {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'warn',
      message,
      data
    };
    
    this.addToHistory(entry);
    console.warn(this.formatMessage('warn', message), data || '');
  }

  error(message: string, error?: Error | any, data?: any) {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'error',
      message,
      data,
      stack: error?.stack
    };
    
    this.addToHistory(entry);
    console.error(this.formatMessage('error', message), error || '', data || '');
    
    // Also log to console group for better visibility
    if (error) {
      console.group('Error Details');
      console.error('Message:', message);
      if (error.stack) {
        console.error('Stack:', error.stack);
      }
      if (data) {
        console.error('Additional Data:', data);
      }
      console.groupEnd();
    }
  }

  // Get all logs for debugging
  getLogs(level?: LogLevel): LogEntry[] {
    if (level) {
      return this.logs.filter(log => log.level === level);
    }
    return [...this.logs];
  }

  // Clear logs
  clearLogs() {
    this.logs = [];
  }

  // Export logs as JSON
  exportLogs(): string {
    return JSON.stringify(this.logs, null, 2);
  }

  // Helper to log API requests
  logApiRequest(method: string, url: string, data?: any) {
    this.debug(`API ${method} ${url}`, data);
  }

  // Helper to log API responses
  logApiResponse(method: string, url: string, status: number, data?: any) {
    const message = `API ${method} ${url} - ${status}`;
    if (status >= 400) {
      this.error(message, data);
    } else {
      this.debug(message, data);
    }
  }

  // Helper to log component lifecycle
  logComponent(component: string, event: string, data?: any) {
    this.debug(`Component ${component} - ${event}`, data);
  }
}

// Create singleton instance
const logger = new Logger();

// Expose logger on window for debugging in development
if (import.meta.env.MODE === 'development') {
  (window as any).logger = logger;
  console.log('🛠️ Logger available at window.logger');
  console.log('Available methods: getLogs(), clearLogs(), exportLogs()');
}

export default logger;