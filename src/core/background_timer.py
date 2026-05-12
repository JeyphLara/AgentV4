import threading
import time
from src.utils.db_manager import DatabaseManager
from src.utils.audio_utils import speak_text

db = DatabaseManager()

def background_worker(callback):
    """Revisa la base de datos cada segundo y llama al callback cuando hay eventos"""
    while True:
        try:
            due_reminders = db.get_due_reminders()
            for rid, user_name, text in due_reminders:
                message = f"Recordatorio para {user_name}: {text}"
                print(f"[TIMER] {message}")
                callback(message)
                db.mark_reminder_done(rid)
            
            expired_timers = db.get_expired_timers()
            for tid, user_name, reason in expired_timers:
                message = f"Temporizador para {user_name}: {reason} ha terminado."
                print(f"[TIMER] {message}")
                callback(message)
                db.mark_timer_expired(tid)
        except Exception as e:
            print(f"[TIMER ERROR] {e}")
        
        time.sleep(5)

def start_background_thread(callback):
    thread = threading.Thread(target=background_worker, args=(callback,), daemon=True)
    thread.start()
    return thread