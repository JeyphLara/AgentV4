import json
from src.skills.reminders_skill import execute as rem_execute
from src.skills.tv_skill import execute as tv_execute
from src.skills.weather_skill import execute as weather_execute
from src.utils.db_manager import DatabaseManager
from src.utils.context_memory import ContextMemory
import os
import time
from google import genai
import mimetypes
from google.genai import types
db = DatabaseManager()

class IntentExecutor:
    """Ejecuta skills basados en intenciones detectadas"""

    def __init__(self):
        self.skill_map = {
            "reminder": self._execute_reminder,
            "play_music": self._execute_play_music,
            "control_device": self._execute_control_device,
            "open_app": self._execute_open_app,
            "weather": self._execute_weather,
            "generate_image": self._execute_generate_image,
            "list_reminders": self._execute_list_reminders,
        }

    def execute(self, intent: str, params: dict, user_name: str = "yo") -> str:
        """
        Ejecuta una skill basada en intención y parámetros.
        
        Args:
            intent: tipo de intención
            params: parámetros extraídos
            user_name: nombre del usuario
            
        Returns:
            Mensaje de confirmación o error
        """
        if intent == "none":
            return None

        handler = self.skill_map.get(intent)
        if not handler:
            print(f"[EXECUTOR] Intención '{intent}' no tiene handler")
            return None

        try:
            result = handler(params, user_name)
            return result
        except Exception as e:
            print(f"[EXECUTOR ERROR] {intent}: {e}")
            return f"Error al ejecutar {intent}: {e}"

    def _execute_reminder(self, params: dict, user_name: str) -> str:
        """Ejecuta intención de recordatorio"""
        task = params.get("task", "")
        time_str = params.get("time", "")

        if not task or not time_str:
            return "Falta información: necesito saber qué recordar y en cuánto tiempo."

        # Construir comando para reminders_skill
        command = f"recuérdame {task} en {time_str}"
        result = rem_execute(user_name, command)
        return result

    def _execute_play_music(self, params: dict, user_name: str) -> str:
        """Ejecuta intención de reproducir música"""
        artist = params.get("artist", "")
        track = params.get("track", "")
        song = params.get("song") or params.get("song_name") or params.get("title") or ""
        music_type = params.get("type", "general")
        playlist = params.get("playlist")
        service = (params.get("platform") or params.get("service") or params.get("app") or params.get("app_name") or "").lower()
        device_query = params.get("device", "")

        if not artist and not track and not song:
            return None  # No ejecutar, dejar que Gemini pregunte

        query = track or song or artist
        device_name = self._find_device(device_query)

        if device_name == "pc":
            if service == "youtube":
                import subprocess
                try:
                    # URL de YouTube Music que auto-reproduce
                    url = f"https://music.youtube.com/search?q={query.replace(' ', '+')}"
                    subprocess.run(["start", url], shell=True)
                    msg = f"Reproduciendo {query} en YouTube Music"
                    print(f"[MUSIC] {msg}")
                    return msg
                except Exception as e:
                    return f"No pude reproducir en YouTube: {e}"
            else:
                import subprocess
                try:
                    subprocess.run(["spotify"], shell=True)
                    msg = f"Abriendo Spotify en tu PC para reproducir {query}"
                    print(f"[MUSIC] {msg}")
                    return msg
                except Exception as e:
                    return f"No pude abrir Spotify en PC: {e}"
        elif device_name:
            import json
            import os
            config_path = os.path.join(os.path.dirname(__file__), '../../config/devices.json')
            try:
                with open(config_path) as f:
                    devices = json.load(f)
            except:
                return "Error al cargar configuración de dispositivos."

            device_info = devices[device_name]
            if device_info.get('type') == 'tv':
                if service == "youtube":
                    result = tv_execute(device_info, "abre youtube")
                    if "Abrí" not in result:
                        return "No pude abrir YouTube en el TV."
                    import time
                    time.sleep(3)
                    tv_execute(device_info, f"busca {query} en youtube")
                    msg = f"Reproduciendo {query} en YouTube en {device_name}"
                    print(f"[MUSIC] {msg}")
                    return msg
                elif service == "spotify":
                    result = tv_execute(device_info, "abre spotify")
                    if "Abrí" not in result:
                        return "No pude abrir Spotify en el TV."
                    import time
                    time.sleep(3)
                    tv_execute(device_info, f"busca {query} en spotify")
                    msg = f"Reproduciendo {query} en Spotify en {device_name}"
                    print(f"[MUSIC] {msg}")
                    return msg
                else:
                    # Si no especificó servicio, asume YouTube para TV
                    result = tv_execute(device_info, "abre youtube")
                    if "Abrí" not in result:
                        return "No pude abrir YouTube en el TV."
                    import time
                    time.sleep(3)
                    tv_execute(device_info, f"busca {query} en youtube")
                    msg = f"Reproduciendo {query} en YouTube en {device_name}"
                    print(f"[MUSIC] {msg}")
                    return msg
            else:
                return f"El dispositivo '{device_name}' no soporta reproducción de música."
        else:
            # Si no se especificó dispositivo pero el comando menciona TV y hay un solo TV, úsalo
            if service == "youtube":
                return self._execute_play_music({"artist": artist, "track": track, "service": "youtube", "device": "tv"}, user_name)
            return f"No encontré un dispositivo que coincida con '{device_query}'."

    def _find_device(self, device_query):
        """Encuentra el mejor dispositivo matching usando normalización y sinónimos"""
        if not device_query or device_query.lower() in ['pc', 'computadora', 'mi pc', 'esta computadora']:
            return 'pc'

        import json
        import os
        import re
        import difflib

        config_path = os.path.join(os.path.dirname(__file__), '../../config/devices.json')
        try:
            with open(config_path) as f:
                devices = json.load(f)
        except:
            return None

        device_names = list(devices.keys())

        def _normalize(text):
            return re.sub(r"[^a-z0-9áéíóúñ ]", "", text.lower())

        def _expand_device_aliases(device_name):
            synonyms = {
                'tv': 'televisor',
                'televisor': 'tv',
                'lámpara': 'lampara',
                'lampara': 'lámpara'
            }
            parts = device_name.split()
            aliases = set([device_name])
            for p in parts:
                if p in synonyms:
                    aliases.add(synonyms[p])
            if 'tv' in device_name and 'televisor' not in device_name:
                aliases.add(device_name.replace('tv', 'televisor'))
            if 'televisor' in device_name and 'tv' not in device_name:
                aliases.add(device_name.replace('televisor', 'tv'))
            return [_normalize(a) for a in aliases]

        command_low = _normalize(device_query)

        # 1. Coincidencia exacta
        for device_name in device_names:
            if _normalize(device_name) == command_low:
                return device_name

        # 2. Coincidencia por partes (incluyendo sinónimos)
        for device_name in device_names:
            aliases = _expand_device_aliases(device_name)
            if all(part in command_low for part in _normalize(device_name).split()):
                return device_name
            for alias in aliases:
                if alias in command_low:
                    return device_name

        # 3. Coincidencia difusa
        matches = difflib.get_close_matches(command_low, [_normalize(n) for n in device_names], n=1, cutoff=0.5)
        if matches:
            normalized_match = matches[0]
            for device_name in device_names:
                if _normalize(device_name) == normalized_match:
                    return device_name

        # 4. Si se menciona un tipo y solo hay un dispositivo de ese tipo, usarlo
        if 'tv' in command_low or 'televisor' in command_low:
            tv_devices = [name for name, info in devices.items() if info.get('type') == 'tv']
            if len(tv_devices) == 1:
                return tv_devices[0]

        if 'luz' in command_low or 'lampara' in command_low or 'lámpara' in command_low:
            light_devices = [name for name, info in devices.items() if info.get('type') == 'light']
            if len(light_devices) == 1:
                return light_devices[0]

        return None

    def _execute_control_device(self, params: dict, user_name: str) -> str:
        """Ejecuta intención de control de dispositivo"""
        device = params.get("device", "").lower()
        action = params.get("action", "")
        percentage = params.get("percentage") or params.get("percent") or params.get("level")

        # Normalizar device para "pc"
        if not device or device in ["pc", "computadora", "ordenador", "computadora personal"]:
            return self._execute_volume_control_pc(action, percentage)

        if "tv" in device or "televisor" in device:
            # Mapear acción a comando para TV
            action_map = {
                "volumen_subir": "sube volumen",
                "volumen_bajar": "baja volumen",
                "mute": "silenciar",
                "power": "enciende",
                "home": "home"
            }
            tv_command = action_map.get(action, action)
            if percentage is not None:
                tv_command = f"volumen {int(percentage)}"
            # Load actual TV IP from devices.json
            import json, os
            config_path = os.path.join(os.path.dirname(__file__), '../../config/devices.json')
            try:
                with open(config_path) as f:
                    devices = json.load(f)
                    for dev_name, dev_info in devices.items():
                        if dev_info.get('type') == 'tv':
                            tv_ip = dev_info.get('ip')
                            result = tv_execute({"type": "tv", "ip": tv_ip}, tv_command)
                            return result
            except Exception as e:
                pass
            result = tv_execute({"type": "tv", "ip": "192.168.1.12:32941"}, tv_command)
            return result

        return f"Dispositivo '{device}' no soportado aún."

    def _execute_volume_control_pc(self, action: str, percentage=None) -> str:
        """Controla el volumen del PC"""
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
        except ImportError:
            return "Error: instala 'pycaw' con: pip install pycaw. O usa comandos sin porcentaje específico."

        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))

            if percentage is not None:
                # Establecer volumen a porcentaje específico (0-100)
                volume.SetMasterVolumeLevelScalar(float(percentage) / 100.0)
                return f"Volumen del PC establecido a {int(percentage)}%"

            action_lower = action.lower()
            if "subir" in action_lower or "aumentar" in action_lower or "+" in action_lower:
                # Subir volumen 10%
                current = volume.GetMasterVolumeLevelScalar()
                new_vol = min(1.0, current + 0.1)
                volume.SetMasterVolumeLevelScalar(new_vol)
                return f"Volumen aumentado a {int(new_vol * 100)}%"
            elif "bajar" in action_lower or "reducir" in action_lower or "-" in action_lower:
                # Bajar volumen 10%
                current = volume.GetMasterVolumeLevelScalar()
                new_vol = max(0.0, current - 0.1)
                volume.SetMasterVolumeLevelScalar(new_vol)
                return f"Volumen reducido a {int(new_vol * 100)}%"
            elif "mute" in action_lower or "silencio" in action_lower:
                volume.SetMute(1)
                return "PC muteado"
            elif "unmute" in action_lower or "desmutear" in action_lower:
                volume.SetMute(0)
                return "Audio del PC activado"
            else:
                return f"No reconozco la acción '{action}' para el volumen del PC"
        except Exception as e:
            return f"Error al controlar volumen del PC: {e}"

    def _execute_open_app(self, params: dict, user_name: str) -> str:
        """Ejecuta intención de abrir app"""
        app_name = (params.get("app") or params.get("app_name") or params.get("service") or params.get("platform") or "").lower()
        device_query = params.get("device", "")

        if not app_name:
            return "Necesito saber qué app abrir."

        device_name = self._find_device(device_query)
        if device_name == "pc":
            if app_name == "youtube" or app_name == "music":
                import subprocess
                try:
                    subprocess.run(["start", "https://music.youtube.com"], shell=True)
                    return "Abriendo YouTube Music en el PC."
                except Exception as e:
                    return f"No pude abrir YouTube en PC: {e}"
            return f"No sé abrir la app '{app_name}' en PC todavía."

        if device_name:
            import json
            import os
            config_path = os.path.join(os.path.dirname(__file__), '../../config/devices.json')
            try:
                with open(config_path) as f:
                    devices = json.load(f)
            except:
                return "Error al cargar configuración de dispositivos."

            device_info = devices[device_name]
            if device_info.get('type') == 'tv':
                result = tv_execute(device_info, f"abre {app_name}")
                return result
            return f"El dispositivo '{device_name}' no soporta abrir apps."

        return f"No encontré un dispositivo que coincida con '{device_query}'."

    def _execute_weather(self, params: dict, user_name: str) -> str:
        """Ejecuta intención de clima"""
        query = params.get("query", "clima")
        city = params.get("city", "Cali")

        result = weather_execute(f"clima en {city}")
        return result

    def _execute_generate_image(self, params: dict, user_name: str) -> str:
        """Ejecuta intención de generar imagen usando Gemini 2.5 Flash Image"""
        description = params.get("description", "")
        if not description:
            return "Necesito una descripción para generar la imagen."

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            model = "gemini-2.5-flash-image"
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=description),
                    ],
                ),
            ]
            generate_content_config = types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            )

            images_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'images')
            os.makedirs(images_dir, exist_ok=True)

            saved_files = []
            file_index = 0
            for chunk in client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.parts is None:
                    continue

                if chunk.parts and chunk.parts[0].inline_data and chunk.parts[0].inline_data.data:
                    inline_data = chunk.parts[0].inline_data
                    data_buffer = inline_data.data
                    file_extension = mimetypes.guess_extension(inline_data.mime_type) or '.png'
                    file_name = f"generated_{int(time.time())}_{file_index}{file_extension}"
                    file_path = os.path.join(images_dir, file_name)
                    with open(file_path, 'wb') as f:
                        f.write(data_buffer)
                    saved_files.append(file_name)
                    file_index += 1
                else:
                    if hasattr(chunk, 'text') and chunk.text:
                        print(f"[Gemini] {chunk.text}")

            if saved_files:
                return f"Imagen generada y guardada como {', '.join(saved_files)} en data/images/."
            return "No se pudo generar la imagen."
        except Exception as e:
            return f"Error al generar imagen: {e}"

    def _execute_list_reminders(self, params: dict, user_name: str) -> str:
        """Ejecuta intención de listar recordatorios pendientes"""
        try:
            pending = db.get_pending_reminders(user_name)
            if not pending:
                return "No tienes recordatorios pendientes."
            
            response = "Tus recordatorios pendientes son:\n"
            for reminder_text, datetime_str in pending:
                from datetime import datetime
                reminder_dt = datetime.fromisoformat(datetime_str)
                now = datetime.utcnow()
                diff = reminder_dt - now
                hours = diff.total_seconds() / 3600
                
                if hours < 1:
                    minutes = int(diff.total_seconds() / 60)
                    response += f"• {reminder_text} (en {minutes} minutos)\n"
                elif hours < 24:
                    h = int(hours)
                    response += f"• {reminder_text} (en {h} horas)\n"
                else:
                    days = int(hours / 24)
                    response += f"• {reminder_text} (en {days} días)\n"
            
            return response.strip()
        except Exception as e:
            print(f"[EXECUTOR ERROR] list_reminders: {e}")
            return f"Error al listar recordatorios: {e}"