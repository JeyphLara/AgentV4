#!/usr/bin/env python3
"""Prueba rápida del DatabaseManager para asegurar que no hay deadlock"""
import sys
from datetime import datetime, timedelta
from src.utils.db_manager import DatabaseManager

print("Inicializando DatabaseManager...")
db = DatabaseManager()

print("Creando un recordatorio de prueba...")
try:
    # Simular crear un recordatorio en 2 minutos
    when = datetime.utcnow() + timedelta(minutes=2)
    db.add_reminder("test_user", "tomar agua", when.isoformat())
    print("[✓] Recordatorio añadido exitosamente")
except Exception as e:
    print(f"[✗] Error: {e}")
    sys.exit(1)

print("Obteniendo recordatorios pendientes...")
try:
    pending = db.get_pending_reminders("test_user")
    print(f"[✓] Recordatorios pendientes: {len(pending)}")
    for text, dt in pending:
        print(f"  - {text} (para {dt})")
except Exception as e:
    print(f"[✗] Error: {e}")
    sys.exit(1)

print("Creando un temporizador de prueba...")
try:
    db.add_timer("test_user", "cocinar", 300)
    print("[✓] Temporizador añadido exitosamente")
except Exception as e:
    print(f"[✗] Error: {e}")
    sys.exit(1)

print("\n[✓✓✓] Todas las pruebas pasaron. No hay deadlock.")
