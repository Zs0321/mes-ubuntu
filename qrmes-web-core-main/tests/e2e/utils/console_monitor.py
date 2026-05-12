# tests/e2e/utils/console_monitor.py
class ConsoleMonitor:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def on_console(self, msg):
        if msg.type == 'error':
            self.errors.append({
                'type': msg.type,
                'text': msg.text,
                'location': msg.location
            })
        elif msg.type == 'warning':
            self.warnings.append({
                'type': msg.type,
                'text': msg.text
            })

    def get_errors(self):
        return self.errors

    def has_errors(self):
        return len(self.errors) > 0
