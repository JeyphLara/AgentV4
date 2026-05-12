import sqlite3
import os
import threading
import json
from datetime import datetime
import numpy as np

VOICE_SIMILARITY_THRESHOLD = 0.90
DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'aurora.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

class DatabaseManager:
    _instance = None
    _lock = threading.RLock()  # RLock = Reentrant Lock, permite al mismo thread adquirirlo varias veces

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS voice_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                voice_embedding TEXT,
                gender TEXT,
                personality TEXT,
                preferences TEXT,
                habits TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        # Asegurar compatibilidad con bases de datos antiguas
        self._ensure_voice_embedding_column()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                datetime_utc TIMESTAMP NOT NULL,
                is_done BOOLEAN DEFAULT 0,
                repeat TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS timers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                start_time_utc TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_expired BOOLEAN DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def _ensure_voice_embedding_column(self):
        self.cursor.execute("PRAGMA table_info(voice_profiles)")
        columns = [row[1] for row in self.cursor.fetchall()]
        if 'voice_embedding' not in columns:
            self.cursor.execute("ALTER TABLE voice_profiles ADD COLUMN voice_embedding TEXT")
            self.conn.commit()

    def get_or_create_user(self, name):
        with self._lock:
            name = name.strip().lower()
            self.cursor.execute("SELECT id FROM users WHERE name = ?", (name,))
            row = self.cursor.fetchone()
            if row:
                return row[0]
            else:
                self.cursor.execute("INSERT INTO users (name) VALUES (?)", (name,))
                self.conn.commit()
                return self.cursor.lastrowid

    def get_profile_by_voice_embedding(self, embedding):
        with self._lock:
            self.cursor.execute("SELECT id, user_id, voice_embedding FROM voice_profiles WHERE voice_embedding IS NOT NULL")
            rows = self.cursor.fetchall()
            best_match = None
            best_similarity = 0.0
            emb = np.array(embedding, dtype=np.float32)
            emb_norm = np.linalg.norm(emb)
            if emb_norm == 0:
                return None
            for row in rows:
                profile_id, user_id, emb_json = row
                stored_emb = np.array(json.loads(emb_json), dtype=np.float32)
                stored_norm = np.linalg.norm(stored_emb)
                if stored_norm == 0:
                    continue
                similarity = float(np.dot(emb, stored_emb) / (emb_norm * stored_norm))
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = profile_id
            if best_similarity >= VOICE_SIMILARITY_THRESHOLD and best_match is not None:
                self.cursor.execute(
                    "SELECT u.name, p.gender, p.personality, p.preferences, p.habits FROM voice_profiles p JOIN users u ON p.user_id = u.id WHERE p.id = ?",
                    (best_match,)
                )
                row = self.cursor.fetchone()
                if row:
                    name, gender, personality, preferences_json, habits_json = row
                    return {
                        'profile': {
                            'name': name,
                            'gender': gender,
                            'personality': personality,
                            'preferences': json.loads(preferences_json) if preferences_json else {},
                            'habits': json.loads(habits_json) if habits_json else {}
                        },
                        'similarity': best_similarity
                    }
            return None

    def create_or_update_profile(self, user_name, voice_embedding=None, gender=None, personality=None, preferences=None, habits=None):
        with self._lock:
            user_id = self.get_or_create_user(user_name)
            self.cursor.execute("SELECT id FROM voice_profiles WHERE user_id = ?", (user_id,))
            row = self.cursor.fetchone()
            emb_json = json.dumps(voice_embedding) if voice_embedding else None
            prefs_json = json.dumps(preferences or {})
            habits_json = json.dumps(habits or {})
            if row:
                profile_id = row[0]
                self.cursor.execute(
                    "UPDATE voice_profiles SET voice_embedding = ?, gender = COALESCE(?, gender), personality = COALESCE(?, personality), preferences = COALESCE(?, preferences), habits = COALESCE(?, habits) WHERE id = ?",
                    (emb_json, gender, personality, prefs_json, habits_json, profile_id)
                )
            else:
                self.cursor.execute(
                    "INSERT INTO voice_profiles (user_id, voice_embedding, gender, personality, preferences, habits) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, emb_json, gender, personality, prefs_json, habits_json)
                )
            self.conn.commit()
            return {'name': user_name, 'gender': gender, 'personality': personality, 'preferences': preferences or {}, 'habits': habits or {}}

    def update_profile_data(self, user_name, preferences=None, habits=None, personality=None):
        with self._lock:
            user_id = self.get_or_create_user(user_name)
            self.cursor.execute("SELECT id, preferences, habits, personality FROM voice_profiles WHERE user_id = ?", (user_id,))
            row = self.cursor.fetchone()
            if not row:
                return None
            profile_id, preferences_json, habits_json, current_personality = row
            prefs = json.loads(preferences_json) if preferences_json else {}
            hab = json.loads(habits_json) if habits_json else {}
            if preferences:
                prefs.update(preferences)
            if habits:
                hab.update(habits)
            personality = personality or current_personality
            self.cursor.execute(
                "SELECT gender FROM voice_profiles WHERE id = ?",
                (profile_id,)
            )
            gender_row = self.cursor.fetchone()
            gender = gender_row[0] if gender_row else None
            self.cursor.execute(
                "UPDATE voice_profiles SET preferences = ?, habits = ?, personality = ? WHERE id = ?",
                (json.dumps(prefs), json.dumps(hab), personality, profile_id)
            )
            self.conn.commit()
            return {
                'name': user_name,
                'gender': gender,
                'personality': personality,
                'preferences': prefs,
                'habits': hab
            }

    def add_profile_note(self, user_name, note):
        with self._lock:
            user_id = self.get_or_create_user(user_name)
            self.cursor.execute("SELECT id, habits FROM voice_profiles WHERE user_id = ?", (user_id,))
            row = self.cursor.fetchone()
            if not row:
                self.create_or_update_profile(user_name)
                habits = {}
            else:
                profile_id, habits_json = row
                habits = json.loads(habits_json) if habits_json else {}
            habits.setdefault('notes', []).append({'timestamp': datetime.utcnow().isoformat(), 'note': note})
            self.update_profile_data(user_name, habits=habits)
            return habits

    def get_profile_by_name(self, user_name):
        with self._lock:
            user_id = self.get_or_create_user(user_name)
            self.cursor.execute(
                "SELECT gender, personality, preferences, habits FROM voice_profiles WHERE user_id = ?",
                (user_id,)
            )
            row = self.cursor.fetchone()
            if not row:
                return None
            gender, personality, preferences_json, habits_json = row
            return {
                'name': user_name,
                'gender': gender,
                'personality': personality,
                'preferences': json.loads(preferences_json) if preferences_json else {},
                'habits': json.loads(habits_json) if habits_json else {}
            }

    def add_reminder(self, user_name, text, datetime_utc, repeat=None):
        with self._lock:
            user_id = self.get_or_create_user(user_name)
            self.cursor.execute(
                "INSERT INTO reminders (user_id, text, datetime_utc, repeat) VALUES (?, ?, ?, ?)",
                (user_id, text, datetime_utc, repeat)
            )
            self.conn.commit()

    def add_timer(self, user_name, reason, duration_seconds):
        with self._lock:
            user_id = self.get_or_create_user(user_name)
            self.cursor.execute(
                "INSERT INTO timers (user_id, reason, duration_seconds) VALUES (?, ?, ?)",
                (user_id, reason, duration_seconds)
            )
            self.conn.commit()
            return self.cursor.lastrowid

    def get_due_reminders(self):
        with self._lock:
            now = datetime.utcnow()
            now_iso = now.isoformat()
            self.cursor.execute(
                "SELECT r.id, u.name, r.text FROM reminders r JOIN users u ON r.user_id = u.id WHERE r.datetime_utc <= ? AND r.is_done = 0 ORDER BY r.datetime_utc ASC",
                (now_iso,)
            )
            return self.cursor.fetchall()

    def get_pending_reminders(self, user_name):
        """Obtiene todos los recordatorios pendientes de un usuario"""
        with self._lock:
            user_id = self.get_or_create_user(user_name)
            now = datetime.utcnow().isoformat()
            self.cursor.execute(
                "SELECT text, datetime_utc FROM reminders WHERE user_id = ? AND is_done = 0 AND datetime_utc > ? ORDER BY datetime_utc ASC",
                (user_id, now)
            )
            return self.cursor.fetchall()

    def mark_reminder_done(self, reminder_id):
        with self._lock:
            self.cursor.execute("UPDATE reminders SET is_done = 1 WHERE id = ?", (reminder_id,))
            self.conn.commit()

    def get_expired_timers(self):
        with self._lock:
            self.cursor.execute(
                "SELECT t.id, u.name, t.reason FROM timers t JOIN users u ON t.user_id = u.id WHERE (datetime(start_time_utc, '+' || duration_seconds || ' seconds') <= datetime('now')) AND is_expired = 0"
            )
            return self.cursor.fetchall()

    def mark_timer_expired(self, timer_id):
        with self._lock:
            self.cursor.execute("UPDATE timers SET is_expired = 1 WHERE id = ?", (timer_id,))
            self.conn.commit()

    def add_conversation_log(self, role, text):
        with self._lock:
            self.cursor.execute(
                "INSERT INTO conversation_log (role, text) VALUES (?, ?)",
                (role, text)
            )
            self.conn.commit()

    def get_recent_conversations(self, limit=10):
        with self._lock:
            self.cursor.execute(
                "SELECT role, text FROM conversation_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            rows = self.cursor.fetchall()
            return [(role, text) for role, text in reversed(rows)]