# src/aurora.py
import asyncio
import sys
import os
import time                     # ← Necesario para mantener el programa vivo
from pathlib import Path

# Añadir la carpeta raíz al path para poder importar módulos
sys.path.append(str(Path(__file__).parent.parent))

from src.core.wake_word_listener import WakeWordListener
from src.core.gemini_assistant import GeminiAssistant
from src.utils.audio_utils import play_notification_sound
from src.utils.db_manager import DatabaseManager

class Aurora:
    """
    La clase principal que orquesta a Aurora.
    """

    def __init__(self):
        # Inicializar los componentes
        self.listener = WakeWordListener(wake_word="aurora", on_activation=self.on_activation)
        self.assistant = GeminiAssistant()
        self.db = DatabaseManager()
        print("¡Aurora está lista! Di 'Aurora' para comenzar.")

    def on_activation(self):
        """
        Esta función se ejecuta cuando se detecta la palabra de activación.
        """
        print("\n*** ¡Aurora activada! ***")
        play_notification_sound("Te escucho...")
        # Crear un nuevo evento loop o usar el existente
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(self._process_command_loop())

    async def _process_command_loop(self):
        """
        El ciclo que maneja la petición del usuario después de la activación.
        """
        # Escuchar el comando del usuario y capturar la huella de voz
        user_prompt, voice_hash = await self.listener.capture_command()
        if not user_prompt:
            print("No te escuché bien. Por favor, intenta de nuevo.")
            return

        # Identificar usuario por voz
        profile = None
        if voice_hash:
            profile = self.db.get_profile_by_voice_hash(voice_hash)

        if not profile:
            print("No reconozco esta voz.")
            user_name = input("¿Cómo quieres que te llame? ").strip()
            if not user_name:
                user_name = "usuario"
            self.db.create_or_update_profile(user_name, voice_hash=voice_hash)
            profile = self.db.get_profile_by_voice_hash(voice_hash)
        else:
            user_name = profile['name']

        print(f"Comando recibido de {user_name}: {user_prompt}")

        # Obtener respuesta de Gemini con contexto de perfil
        response_text, response_audio = await self.assistant.get_response(user_prompt, user_profile=profile)

        if response_audio:
            print(f"Aurora: {response_text}")
            # La reproducción de audio ya se maneja dentro de get_response
        else:
            print("Lo siento, no pude generar una respuesta de audio.")

    def run(self):
        """
        Inicia el bucle principal de escucha continua.
        """
        try:
            self.listener.start_listening()
            # Mantener el programa corriendo indefinidamente
            while True:
                time.sleep(1)   # Pequeña pausa para no saturar la CPU
        except KeyboardInterrupt:
            print("\nApagando a Aurora. ¡Hasta luego!")
            self.listener.stop_listening()


if __name__ == "__main__":
    aurora = Aurora()
    aurora.run()