from collections import deque
from datetime import datetime, timedelta

class ContextMemory:
    def __init__(self, max_size=10, ttl_seconds=300):
        self.buffer = deque(maxlen=max_size)
        self.ttl = ttl_seconds

    def add(self, role, text):
        self.buffer.append({
            'role': role,
            'text': text,
            'timestamp': datetime.now()
        })

    def get_recent(self):
        now = datetime.now()
        recent = [f"{item['role']}: {item['text']}" for item in self.buffer if (now - item['timestamp']).total_seconds() < self.ttl]
        return "\n".join(recent) if recent else None

    def clear(self):
        self.buffer.clear()