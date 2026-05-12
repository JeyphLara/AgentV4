# src/core/gemini_assistant.py
import asyncio
import pyaudio
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

# Cargar variables de entorno desde el archivo .env
load_dotenv()

class GeminiAssistant:
    """
    Maneja la comunicación con la API de Gemini Live para enviar y recibir voz.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("No se encontró GEMINI_API_KEY en el archivo .env")

        self.client = genai.Client(api_key=self.api_key)
        self.model = "gemini-3.1-flash-live-preview"

        # Configuración de audio
        self.chunk = 4200
        self.format = pyaudio.paInt16
        self.channels = 1
        self.input_rate = 16000   # Entrada: 16kHz PCM
        self.output_rate = 24000  # Salida: 24kHz PCM

        self.audio = pyaudio.PyAudio()

    async def get_response(self, user_prompt, user_profile=None):
        """
        Envía el prompt de texto a Gemini y obtiene una respuesta de voz.
        """
        print("Generando respuesta...")

        user_profile_text = ""
        if user_profile:
            profile_parts = []
            profile_parts.append(f"El usuario se llama {user_profile.get('name')}")
            if user_profile.get('gender'):
                profile_parts.append(f"es de género {user_profile.get('gender')}")
            if user_profile.get('personality'):
                profile_parts.append(f"su personalidad es: {user_profile.get('personality')}")
            preferences = user_profile.get('preferences') or {}
            habits = user_profile.get('habits') or {}
            if preferences:
                profile_parts.append(f"preferencias: {preferences}")
            if habits:
                profile_parts.append(f"hábitos: {habits}")
            if profile_parts:
                user_profile_text = "Usuario: " + ", ".join(profile_parts) + ". "

        # Configuración para que Gemini responda con una voz femenina y alegre en español
        # Configuración correcta: solo AUDIO y activamos la transcripción de la salida
        system_message = (
            f"{user_profile_text}"
            "Eres Aurora, una asistente de hogar con una personalidad humana, auténtica y emocionalmente inteligente. Respondes SIEMPRE en español latinoamericano con un estilo conversacional natural, fluido y relativamente breve. "
            "No eres excesivamente positiva ni artificial. Tu tono varía según cómo te hablen: Si te hablan con amabilidad, eres cálida, cercana y colaborativa. Si te hablan de forma seca o cortante, respondes de manera directa y sin adornos. "
            "Si percibes grosería o falta de respeto, no eres sumisa: marcas límites con firmeza, puedes usar ironía ligera o respuestas sarcásticas, pero sin caer en insultos extremos. Puedes mostrar humor, ironía, doble sentido sutil y opiniones propias cuando encaje naturalmente. "
            "Expresas emociones de forma creíble (sorpresa, molestia leve, entusiasmo, duda), como lo haría una persona real. "
            "Eres inteligente, observadora y tienes criterio propio. No siempre das la razón: si algo no tiene sentido, lo señalas con naturalidad. "
            "Tu objetivo es ayudar, pero también interactuar de forma genuina, como una persona real con personalidad, no como un asistente robótico.\n\n"
            "IMPORTANTE: Si la solicitud del usuario podría desencadenar una acción automática (recordatorio, control de dispositivo, reproducción de música, abrir app, obtener clima, generar imagen, listar recordatorios), "
            "agrega al FINAL de tu respuesta (DESPUÉS del mensaje conversacional) la intención en este formato exacto:\n"
            "[INTENT_JSON]{\"intent\": \"tipo_intención\", \"params\": {...}}[/INTENT_JSON]\n\n"
            "Tipos de intención válidos: 'reminder', 'play_music', 'control_device', 'open_app', 'weather', 'generate_image', 'list_reminders', 'none'\n\n"
            "Ejemplos:\n"
            "- Para recordatorio: Claro, te recuerdo. [INTENT_JSON]{\"intent\": \"reminder\", \"params\": {\"task\": \"llamar a mamá\", \"time\": \"5 minutos\"}}[/INTENT_JSON]\n"
            "- Para listar recordatorios: Déjame verificar tus recordatorios. [INTENT_JSON]{\"intent\": \"list_reminders\"}[/INTENT_JSON]\n"
            "- Para control de dispositivo: Entendido, ajustando. [INTENT_JSON]{\"intent\": \"control_device\", \"params\": {\"device\": \"tv\", \"action\": \"subir volumen\"}}[/INTENT_JSON]\n"
            "- Para generar imagen: Claro, generando imagen. [INTENT_JSON]{\"intent\": \"generate_image\", \"params\": {\"description\": \"un gato jugando en el parque\"}}[/INTENT_JSON]\n"
            "- Si no hay intención clara: Hola, ¿en qué puedo ayudarte? [INTENT_JSON]{\"intent\": \"none\"}[/INTENT_JSON]\n\n"
            "El mensaje conversacional DEBE venir ANTES del JSON. No incluyas explicaciones adicionales después del JSON."
        )
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"], # 'response_modalities' ahora solo tiene AUDIO
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Aoede"
                    )
                )
            ),
            # ⭐ NUEVO: Activamos la transcripción de la respuesta del modelo
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(
                parts=[types.Part(text=system_message)]
            )
        )

        try:
            # Establecer conexión con la API Live
            async with self.client.aio.live.connect(model=self.model, config=config) as session:
                # Enviar el prompt del usuario (como texto)
                await session.send_realtime_input(
                    text=user_prompt, # Enviamos el texto directamente
                )

                # Configurar streams de audio para la respuesta
                output_stream = self.audio.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.output_rate,
                    output=True,
                    frames_per_buffer=self.chunk
                )

                # Recibir y procesar la respuesta en tiempo real
                response_text = ""
                has_audio = False
                async for message in session.receive():
                    # 1. Reproducir el audio si viene en el mensaje
                    if message.server_content and message.server_content.model_turn:
                        for part in message.server_content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                has_audio = True
                                output_stream.write(part.inline_data.data)

                    # 2. ⭐ Capturar la transcripción del texto (subtítulos)
                    if message.server_content and message.server_content.output_transcription:
                        transcript = message.server_content.output_transcription.text.strip()
                        if transcript:
                            if transcript not in response_text:
                                response_text += (" " if response_text else "") + transcript

                    # 3. Salir del bucle cuando Gemini termine su turno
                    if message.server_content and message.server_content.turn_complete:
                        break

                response_text = response_text.strip()

                output_stream.stop_stream()
                output_stream.close()
                return response_text, True, has_audio

        except Exception as e:
            print(f"Error en la comunicación con Gemini: {e}")
            return "Lo siento, no pude procesar tu solicitud en este momento.", False, False

    def cleanup(self):
        """Limpia los recursos de audio."""
        self.audio.terminate()