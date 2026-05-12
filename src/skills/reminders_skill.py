import re
from datetime import datetime, timedelta
from src.utils.db_manager import DatabaseManager

db = DatabaseManager()

# Mapeo de números en texto a dígitos
TEXT_TO_NUMBER = {
    'un': 1, 'una': 1, 'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
    'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10,
    'once': 11, 'doce': 12, 'trece': 13, 'catorce': 14, 'quince': 15,
    'veinte': 20, 'treinta': 30, 'cuarenta': 40, 'cincuenta': 50,
    'sesenta': 60, 'setenta': 70, 'ochenta': 80, 'noventa': 90,
    'cien': 100,
    'half': 0.5, 'media': 0.5, 'medio': 0.5,
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
}

WEEKDAYS = {
    'lunes': 0, 'martes': 1, 'miércoles': 2, 'miercoles': 2, 'jueves': 3,
    'viernes': 4, 'sábado': 5, 'sabado': 5, 'domingo': 6
}

MONTHS = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5,
    'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10,
    'noviembre': 11, 'diciembre': 12
}

def _text_to_number(text):
    """Convierte números en texto a dígitos, soporta 'veintiuno' y términos en inglés."""
    text = text.lower().strip()
    if text in TEXT_TO_NUMBER:
        return TEXT_TO_NUMBER[text]
    # Para valores como "veintiuno" o "veintidos"
    for word, num in TEXT_TO_NUMBER.items():
        if text.startswith(word):
            remainder = text[len(word):]
            if remainder in TEXT_TO_NUMBER:
                return num + TEXT_TO_NUMBER[remainder]
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return None

def _normalize_command_text(text):
    """Normaliza variantes naturales de comandos de recordatorio y unidades mixtas."""
    text = text.lower().strip()
    # Frases equivalentes a 'recuérdame'
    text = re.sub(r'\bquiero que me recuerdes\b', 'recuérdame', text)
    text = re.sub(r'\bquieres que me recuerdes\b', 'recuérdame', text)
    text = re.sub(r'\bme recuerdes\b', 'recuérdame', text)
    text = re.sub(r'\brecuerda\b', 'recuérdame', text)
    text = re.sub(r'\bdentro de\b', 'en', text)
    text = text.replace('no se te a olvidar', 'no se te va a olvidar')

    # Unidades en inglés y variaciones
    text = re.sub(r'\bminutes?\b', 'minutos', text)
    text = re.sub(r'\bhours?\b', 'horas', text)
    text = re.sub(r'\bminute\b', 'minuto', text)
    text = re.sub(r'\bhour\b', 'hora', text)
    text = re.sub(r'\bseconds?\b', 'segundos', text)
    text = re.sub(r'\bsecs?\b', 'segundos', text)
    text = re.sub(r'\bhalf an hour\b', 'media hora', text)
    text = re.sub(r'\bhalf hour\b', 'media hora', text)
    text = re.sub(r'\bhalf\b', 'media', text)

    # Normalizar am/pm
    text = re.sub(r'\ba\.m\.|\bam\b', 'am', text)
    text = re.sub(r'\bp\.m\.|\bpm\b', 'pm', text)
    return text

def _parse_datetime_with_date(text):
    """Analiza fechas explícitas como '27 de mayo a las 2:00pm'."""
    text = text.lower()
    date_match = re.search(r'(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)(?:\s+de\s+(\d{4}))?', text)
    if not date_match:
        return None

    day = int(date_match.group(1))
    month = MONTHS.get(date_match.group(2))
    year = int(date_match.group(3)) if date_match.group(3) else datetime.utcnow().year

    time_match = re.search(r'a\s+las?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2)) if time_match.group(2) else 0
    period = time_match.group(3)
    if period == 'pm' and hour < 12:
        hour += 12
    elif period == 'am' and hour == 12:
        hour = 0

    try:
        target = datetime(year, month, day, hour, minute, 0, 0)
    except Exception:
        return None

    now = datetime.utcnow()
    if target < now and not date_match.group(3):
        target = target.replace(year=year + 1)
    return target

def _parse_time(time_str):
    """Convierte expresiones de hora a datetime."""
    time_str = time_str.lower().strip()
    time_str = time_str.replace('.', '').replace('a m', 'am').replace('p m', 'pm')

    date_time = _parse_datetime_with_date(time_str)
    if date_time:
        return date_time

    if re.search(r'\b(media|medio)\s+hora\b', time_str):
        return datetime.utcnow() + timedelta(minutes=30)
    if re.search(r'\b(media|medio)\s+minuto\b', time_str):
        return datetime.utcnow() + timedelta(seconds=30)

    match = re.search(r'las?\s+(\d+)\s+(?:y\s+(\d+))?\s+(?:de\s+la\s+)?(tarde|mañana|madrugada|noche|mañana)', time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        period = match.group(3).lower()

        if period in ['tarde', 'noche']:
            if hour < 12:
                hour += 12
        elif period in ['mañana', 'madrugada']:
            if hour >= 12:
                hour -= 12

        now = datetime.utcnow()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        return target

    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        period = match.group(3)

        if period == 'pm' and hour < 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0

        now = datetime.utcnow()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        return target

    return None

def _parse_weekday_time(text):
    """Extrae día de la semana y hora de un texto como 'viernes 5 de abril a las 1 de la tarde'"""
    text = text.lower()
    
    # Buscar día de la semana
    weekday = None
    for day_name, day_num in WEEKDAYS.items():
        if day_name in text:
            weekday = day_num
            break
    
    if weekday is None:
        return None
    
    # Buscar hora
    time_match = re.search(r'(?:a\s+)?las?\s+(\d+)\s+(?:y\s+(\d+))?\s+(?:de\s+la\s+)?(tarde|mañana|noche|madrugada)?', text)
    if not time_match:
        return None
    
    hour = int(time_match.group(1))
    minute = int(time_match.group(2)) if time_match.group(2) else 0
    period = time_match.group(3) or "tarde"
    
    if period in ['tarde', 'noche']:
        if hour < 12:
            hour += 12
    elif period in ['mañana', 'madrugada']:
        if hour >= 12:
            hour -= 12
    
    # Calcular el próximo día especificado
    now = datetime.utcnow()
    current_weekday = now.weekday()
    days_ahead = (weekday - current_weekday) % 7
    if days_ahead == 0:  # Si es hoy, solo si la hora no ha pasado
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            days_ahead = 7
    else:
        target = now + timedelta(days=days_ahead)
        target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    if days_ahead > 0:
        target = now + timedelta(days=days_ahead)
        target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    return target

def execute(user_name, command_text):
    text = _normalize_command_text(command_text)
    print(f"[DEBUG] reminders_skill: '{text}'")

    # Limpiar palabras iniciales innecesarias
    text = re.sub(r'^(recuerda|ok|bueno|dale|perfecto)\s+', '', text)
    
    # LISTAR RECORDATORIOS PENDIENTES: "¿cuáles son mis recordatorios?" o "lista de recordatorios"
    if any(phrase in text for phrase in ['cuales son', 'cuales', 'lista de recordatorios', 'mis recordatorios', 'recordatorios pendientes']):
        try:
            pending = db.get_pending_reminders(user_name)
            if not pending:
                return "No tienes recordatorios pendientes."
            response = "Tus recordatorios pendientes son:\n"
            for reminder_text, datetime_str in pending:
                reminder_dt = datetime.fromisoformat(datetime_str)
                now = datetime.utcnow()
                diff = reminder_dt - now
                hours = diff.total_seconds() / 3600
                if hours < 1:
                    minutes = int(diff.total_seconds() / 60)
                    response += f"- {reminder_text} (en {minutes} minutos)\n"
                else:
                    h = int(hours)
                    response += f"- {reminder_text} (en {h} horas)\n"
            return response.strip()
        except Exception as e:
            print(f"[ERROR] get_pending_reminders: {e}")
            return f"Error al listar recordatorios: {e}"
    
    # Patrón 1: "recuérdame <texto> en <N> <unidad>"
    match = re.search(r'recu[eé]rdame\s+(.+?)\s+en\s+(\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|one|two|three|four|five|six|seven|eight|nine|ten|media|medio)\s+(segundos?|minutos?|horas?)', text)
    if match:
        reminder_text = match.group(1).strip()
        amount_text = match.group(2)
        unit = match.group(3)
        amount = _text_to_number(amount_text)
        if amount is None:
            return f"No entendí el número '{amount_text}'. Usa números como '1' o 'un'."
        if not reminder_text:
            return "¿Qué deberías recordar?"
        try:
            delta = _parse_delta(amount, unit)
            when = datetime.utcnow() + delta
            db.add_reminder(user_name, reminder_text, when.isoformat())
            return f"Listo, te recordaré '{reminder_text}' en {amount} {unit}."
        except Exception as e:
            print(f"[ERROR] db.add_reminder: {e}")
            return f"Error al guardar el recordatorio: {e}"

    # Patrón 2: "recuérdame en <N> <unidad> <texto>"
    match = re.search(r'recu[eé]rdame\s+en\s+(\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|one|two|three|four|five|six|seven|eight|nine|ten|media|medio)\s+(segundos?|minutos?|horas?)\s+(.+)', text)
    if match:
        amount_text = match.group(1)
        unit = match.group(2)
        reminder_text = match.group(3).strip()
        amount = _text_to_number(amount_text)
        if amount is None:
            return f"No entendí el número '{amount_text}'. Usa números como '1' o 'un'."
        try:
            delta = _parse_delta(amount, unit)
            when = datetime.utcnow() + delta
            db.add_reminder(user_name, reminder_text, when.isoformat())
            return f"Listo, te recordaré '{reminder_text}' en {amount} {unit}."
        except Exception as e:
            print(f"[ERROR] db.add_reminder: {e}")
            return f"Error al guardar el recordatorio: {e}"

    # Patrón 3b: "recuérdame a las <HORA> <texto>"
    match = re.search(r'recu[eé]rdame\s+a\s+(las?.+?)\s+(.+)', text)
    if match:
        time_str = match.group(1)
        reminder_text = match.group(2).strip()
        try:
            when = _parse_time(time_str)
            if when:
                db.add_reminder(user_name, reminder_text, when.isoformat())
                return f"Listo, te recordaré '{reminder_text}' a esa hora."
            else:
                return "No entendí la hora. Usa formatos como 'a las 2 de la tarde' o 'a las 14:30'."
        except Exception as e:
            print(f"[ERROR] patrón hora inicio: {e}")
            return f"Error al procesar la hora: {e}"

    # Patrón 3c: "recuérdame el 27 de mayo a las 2:00pm <texto>"
    match = re.search(r'recu[eé]rdame\s+(?:el\s+)?(\d{1,2}\s+de\s+\w+\s+a\s+las?\s*\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?)\s+(.+)', text)
    if match:
        time_str = match.group(1)
        reminder_text = match.group(2).strip()
        try:
            when = _parse_time(time_str)
            if when:
                db.add_reminder(user_name, reminder_text, when.isoformat())
                return f"Listo, te recordaré '{reminder_text}' en esa fecha y hora."
            else:
                return "No entendí la fecha y hora. Usa un formato como '27 de mayo a las 2:00pm'."
        except Exception as e:
            print(f"[ERROR] patrón fecha: {e}")
            return f"Error al procesar la fecha: {e}"

    # Patrón 3: "recuérdame <texto> a las <HORA>"
    match = re.search(r'recu[eé]rdame\s+(.+?)\s+a\s+(las?\s*\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?(?:\s+de\s+la\s+(?:tarde|mañana|noche|madrugada))?)$', text)
    if match:
        time_str = match.group(1)
        reminder_text = match.group(2).strip()
        try:
            when = _parse_time(time_str)
            if when:
                db.add_reminder(user_name, reminder_text, when.isoformat())
                return f"Listo, te recordaré '{reminder_text}' en esa fecha y hora."
            else:
                return "No entendí la fecha y hora. Usa un formato como '27 de mayo a las 2:00pm'."
        except Exception as e:
            print(f"[ERROR] patrón fecha: {e}")
            return f"Error al procesar la fecha: {e}"

    # Patrón 3d: "recuérdame media hora <texto>"
    match = re.search(r'recu[eé]rdame\s+(?:media|medio)\s+(hora|minuto)s?\s+(?:para\s+)?(.+)', text)
    if match:
        unit = match.group(1)
        reminder_text = match.group(2).strip()
        try:
            delta = _parse_delta(0.5, unit)
            when = datetime.utcnow() + delta
            db.add_reminder(user_name, reminder_text, when.isoformat())
            return f"Listo, te recordaré '{reminder_text}' en media {unit}."
        except Exception as e:
            print(f"[ERROR] patrón media: {e}")
            return f"Error al procesar el recordatorio: {e}"

    # Patrón 4: Recordatorios para días específicos con anticipación (ej: "tengo cita el viernes a las 2, recuérdame 20 minutos antes")
    if 'cita' in text or 'programada' in text or 'en el' in text:
        # Extraer la hora y día de la cita
        cita_match = re.search(r'(?:el\s+)?(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\s+.*?\s+(?:a\s+)?las?\s+(\d+)(?:\s+y\s+(\d+))?', text)
        if cita_match:
            # Buscar la solicitud de anticipación
            anticipation_match = re.search(r'recu[eé]rdame\s+(\d+|un|una|dos)\s+(minuto|minutos|hora|horas)\s+antes', text)
            if anticipation_match:
                amount_text = anticipation_match.group(1)
                unit = anticipation_match.group(2)
                amount = _text_to_number(amount_text)
                
                # Extraer info de cita
                weekday_name = cita_match.group(1)
                hour = int(cita_match.group(2))
                minute = int(cita_match.group(3)) if cita_match.group(3) else 0
                
                try:
                    # Encontrar la próxima ocurrencia del día
                    weekday_num = WEEKDAYS.get(weekday_name, -1)
                    if weekday_num == -1:
                        return "No reconozco ese día de la semana."
                    
                    now = datetime.utcnow()
                    current_weekday = now.weekday()
                    days_ahead = (weekday_num - current_weekday) % 7
                    if days_ahead == 0:
                        days_ahead = 0
                    
                    cita_time = now + timedelta(days=days_ahead)
                    cita_time = cita_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    
                    # Restar los minutos/horas de anticipación
                    delta = _parse_delta(amount, unit)
                    reminder_time = cita_time - delta
                    
                    if reminder_time > now:
                        db.add_reminder(user_name, f"Cita programada en {(reminder_time + delta).strftime('%A a las %H:%M')}", reminder_time.isoformat())
                        return f"Listo, te recordaré {amount} {unit} antes de tu cita del {weekday_name} a las {hour}:{minute:02d}."
                    else:
                        return "La cita ya pasó o la anticipación es muy larga."
                except Exception as e:
                    print(f"[ERROR] cita: {e}")
                    return f"Error al procesar la cita: {e}"

    # Patrón 5: "recordatorio <texto> en <N> <unidad>"
    match = re.search(r'recordatorio[s]?\s+([^e][^n]*?)\s+en\s+(\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+(segundo|segundos|minuto|minutos|hora|horas)', text)
    if match:
        reminder_text = match.group(1).strip()
        amount_text = match.group(2)
        unit = match.group(3)
        amount = _text_to_number(amount_text)
        if amount is None:
            return f"No entendí el número '{amount_text}'. Usa números como '1' o 'un'."
        try:
            delta = _parse_delta(amount, unit)
            when = datetime.utcnow() + delta
            db.add_reminder(user_name, reminder_text, when.isoformat())
            return f"Perfecto, te recordaré '{reminder_text}' en {amount} {unit}."
        except Exception as e:
            print(f"[ERROR] db.add_reminder: {e}")
            return f"Error al guardar el recordatorio: {e}"

    # Mensaje de recordatorio incompleto
    if text.startswith('recuerdame') or text.startswith('recuérdame') or text.startswith('recordatorio'):
        if 'en' not in text and 'para' not in text and 'a' not in text:
            return "Necesito un tiempo para el recordatorio, por ejemplo: 'recuérdame llamar a mamá en 10 minutos' o 'recuérdame X a las 2 de la tarde'."

    # Temporizador: "temporizador de <N> <unidad> para <razón>"
    match = re.search(r'temporizador\s+de\s+(\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+(segundo|segundos|minuto|minutos|hora|horas)\s+para\s+(.+)', text)
    if match:
        amount_text = match.group(1)
        unit = match.group(2)
        reason = match.group(3).strip()
        amount = _text_to_number(amount_text)
        if amount is None:
            return f"No entendí el número '{amount_text}'. Usa números como '1' o 'un'."
        try:
            delta = _parse_delta(amount, unit)
            seconds = int(delta.total_seconds())
            db.add_timer(user_name, reason, seconds)
            return f"Temporizador de {amount} {unit} activado para: {reason}."
        except Exception as e:
            print(f"[ERROR] db.add_timer: {e}")
            return f"Error al crear el temporizador: {e}"

    return None

def _parse_delta(amount, unit):
    unit = unit.lower()
    if unit.startswith('seg'):
        return timedelta(seconds=float(amount))
    elif unit.startswith('min'):
        return timedelta(minutes=float(amount))
    elif unit.startswith('hor'):
        return timedelta(hours=float(amount))
    else:
        return timedelta(seconds=float(amount))  # fallback