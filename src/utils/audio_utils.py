import platform
import subprocess
import winsound  # para Windows
import threading

def play_notification_sound(sound_type):
    """Reproduce un sonido de notificación (beep en Windows)"""
    try:
        if platform.system() == "Windows":
            # Sonido de sistema 'Asterisk' (puedes cambiarlo)
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
        else:
            print(f"🔊 [Sonido de {sound_type}]")
    except:
        pass

def speak_text(text):
    """Sintetiza voz usando Gemini TTS con reintentos"""
    if not text or not text.strip():
        return

    def _speak_with_gemini():
        max_retries = 3
        for attempt in range(max_retries):
            try:
                from src.core.gemini_assistant import GeminiAssistant
                assistant = GeminiAssistant()

                # Prompt simple para TTS
                prompt = f"""Eres Aurora, una asistente personal. Di exactamente este texto de forma natural y conversacional:

"{text}"

No añadas explicaciones ni comentarios adicionales."""

                # Usar get_response con audio activado
                import asyncio
                response_text, success, has_audio = asyncio.run(assistant.get_response(prompt))
                if success and has_audio:
                    return  # Éxito, salir
                else:
                    print(f"[TTS RETRY] Intento {attempt + 1}/{max_retries} falló, reintentando...")
                    import time
                    time.sleep(1)  # Esperar 1 segundo antes de reintentar
            except Exception as e:
                print(f"[TTS ERROR] Intento {attempt + 1}/{max_retries}: {e}")
                import time
                time.sleep(1)

        # Si todos los reintentos fallan, usar SAPI como último recurso
        print("[TTS FALLBACK] Usando SAPI local después de reintentos")
        _speak_with_sapi(text)

    def _speak_with_sapi(text):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak(text)
            pythoncom.CoUninitialize()
        except Exception as e:
            print(f"Error en TTS SAPI: {e}")

    # Ejecutar en hilo separado para no bloquear
    threading.Thread(target=_speak_with_gemini, daemon=True).start()