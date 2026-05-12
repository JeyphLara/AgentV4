import asyncio
import sys
import os
import time
import threading
import re
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.core.wake_word_listener import WakeWordListener
from src.core.gemini_assistant import GeminiAssistant
from src.core.skill_manager import SkillManager
from src.core.background_timer import start_background_thread
from src.core.intent_detector import IntentDetector
from src.core.intent_executor import IntentExecutor
from src.utils.audio_utils import play_notification_sound, speak_text
from src.utils.db_manager import DatabaseManager
from src.utils.context_memory import ContextMemory

class Aurora:
    def __init__(self):
        self.listener = WakeWordListener(wake_word="aurora", on_activation=self.on_activation)
        self.assistant = GeminiAssistant()
        self.skill_manager = SkillManager()
        self.db = DatabaseManager()
        self.memory = ContextMemory()
        self.intent_detector = IntentDetector()
        self.intent_executor = IntentExecutor()
        # Iniciar hilo de recordatorios
        self.bg_thread = start_background_thread(self.on_reminder)
        # Estado para completar comandos
        self.pending_command = None  # Comando incompleto esperando respuesta
        self.last_user_prompt = None
        self.last_gemini_response = None
        print("¡Aurora está lista! Di 'Aurora' para comenzar.")

    def on_reminder(self, message):
        """Callback que se ejecuta cuando un recordatorio o temporizador expira"""
        print(f"\n🔔 {message}")
        
        def _handle_reminder_with_gemini():
            """Ejecuta Gemini en un hilo separado para no bloquear"""
            try:
                gemini_prompt = f"""Eres un asistente personal amable llamado Aurora. El usuario tiene un recordatorio vencido.

El recordatorio es: "{message}"

Responde de forma natural, cálida y breve informando el recordatorio. 
Habla directamente con el usuario como si fueras su asistente personal.
No hagas explicaciones extra, solo comunica lo que debe recordar de forma conversacional."""
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response_text, success, has_audio = loop.run_until_complete(
                    self.assistant.get_response(gemini_prompt)
                )
                loop.close()
                
                if success and response_text:
                    # Limpiar etiquetas de intención si Gemini las incluye
                    response_text = re.sub(r'\[INTENT_JSON\].*?\[/INTENT_JSON\]', '', response_text, flags=re.DOTALL).strip()
                    print(f"⏰ Aurora: {response_text}")
                    if not has_audio:
                        speak_text(response_text)
                else:
                    # Fallback si Gemini falla o no hay texto válido
                    speak_text(message)
            except Exception as e:
                print(f"[REMINDER ERROR] {e}")
                speak_text(message)
        
        # Ejecutar en un hilo separado para no bloquear
        reminder_thread = threading.Thread(target=_handle_reminder_with_gemini, daemon=True)
        reminder_thread.start()

    def on_activation(self):
        print("\n*** ¡Aurora activada! ***")
        play_notification_sound("Dime...")
        asyncio.run(self._conversation_loop())

    def _extract_user_profile_info(self, user_name, user_prompt):
        lower_prompt = user_prompt.lower()
        preferences = {}
        habits = {}

        likes_match = re.search(r'(?:me gusta|me gustan|mi favorita es|mi favorito es|amo)\s+(.+?)(?:[.,]|$)', lower_prompt)
        if likes_match:
            preferences.setdefault('likes', []).append(likes_match.group(1).strip())

        dislikes_match = re.search(r'(?:odio|no me gusta|no me gustan)\s+(.+?)(?:[.,]|$)', lower_prompt)
        if dislikes_match:
            preferences.setdefault('dislikes', []).append(dislikes_match.group(1).strip())

        prefere_match = re.search(r'prefiero\s+(.+?)(?:[.,]|$)', lower_prompt)
        if prefere_match:
            preferences.setdefault('prefers', []).append(prefere_match.group(1).strip())

        if 'rutina' in lower_prompt or 'hábito' in lower_prompt or 'habit' in lower_prompt:
            habits.setdefault('notes', []).append({'timestamp': datetime.utcnow().isoformat(), 'note': user_prompt})

        if preferences or habits:
            self.db.update_profile_data(user_name, preferences=preferences if preferences else None, habits=habits if habits else None)

    async def _conversation_loop(self):
        desconectar_intentos = 0
        while True:
            user_prompt, voice_embedding = await self.listener.capture_command()
            if not user_prompt:
                desconectar_intentos += 1
                if desconectar_intentos >= 2:
                    print("No te escuché, cerrando conversación por inactividad.")
                    break
                continue

            desconectar_intentos = 0
            user_prompt = user_prompt.strip()
            print(f"Comando recibido: {user_prompt}")

            # Identificar usuario por voz
            profile = None
            if voice_embedding:
                voice_match = self.db.get_profile_by_voice_embedding(voice_embedding)
                if voice_match is not None:
                    profile = voice_match['profile']
                    similarity = voice_match['similarity']
                    print(f"[VOICE] similitud de voz: {similarity:.3f} -> {profile['name']}")
                    if similarity < 0.92:
                        print("No reconozco esta voz con suficiente confianza.")
                        profile = None
                else:
                    print("No reconozco esta voz.")

            if not profile:
                user_name = input("¿Cómo quieres que te llame? ").strip()
                if not user_name:
                    user_name = "usuario"
                self.db.create_or_update_profile(user_name, voice_embedding=voice_embedding)
                voice_match = self.db.get_profile_by_voice_embedding(voice_embedding)
                if voice_match is not None:
                    profile = voice_match['profile']
                    user_name = profile['name']
                else:
                    profile = {'name': user_name, 'preferences': {}, 'habits': {}}
            else:
                user_name = profile['name']

            self._extract_user_profile_info(user_name, user_prompt)

            # Salir del modo conversacional con palabras clave
            if user_prompt.lower() in ["adiós", "adios", "hasta luego", "gracias", "basta", "termina"]:
                speak_text("Entendido, regreso al modo de espera.")
                break

            self.memory.add("usuario", user_prompt)
            self.db.add_conversation_log("usuario", user_prompt)

            # Intentar con skills
            try:
                skill_response = self.skill_manager.handle(user_name, user_prompt)
                if skill_response:
                    print(f"Aurora: {skill_response}")
                    self.memory.add("aurora", skill_response)
                    self.db.add_conversation_log("aurora", skill_response)
                    speak_text(skill_response)
                    continue
            except Exception as e:
                print(f"[SKILL ERROR] {e}")
                speak_text(f"Error al procesar el comando: {e}")
                continue

            # Si no, usar Gemini con contexto
            context = self.memory.get_recent()
            full_prompt = user_prompt
            if context:
                full_prompt = f"Contexto de conversación reciente:\n{context}\n\nUsuario: {user_prompt}\nAurora:"

            response_text, success, has_audio = await self.assistant.get_response(full_prompt, user_profile=profile)
            if success and response_text:
                # Extraer intención primero para limpiar el mensaje
                intent_result = self.intent_detector.extract_intent_from_response(response_text)
                response_message = intent_result['message'].strip() or response_text.strip()

                if response_message:
                    print(f"Aurora: {response_message}")
                    self.memory.add("aurora", response_message)
                    self.db.add_conversation_log("aurora", response_message)
                    # Si no hubo audio de Gemini, usar TTS local
                    if not has_audio:
                        speak_text(response_message)
                    self.last_user_prompt = user_prompt
                    self.last_gemini_response = response_message
                    # No llamar a speak_text aquí: Gemini ya produce la voz

                # Intentar ejecutar intención automáticamente
                try:
                    if intent_result.get("intent") != "none":
                        print(f"[AUTOEXEC] Ejecutando intención detectada: {intent_result}")
                        exec_result = self.intent_executor.execute(
                            intent_result["intent"],
                            intent_result.get("params", {}),
                            user_name
                        )
                        if exec_result:
                            print(f"Sistema: {exec_result}")
                            self.memory.add("sistema", exec_result)
                            self.db.add_conversation_log("sistema", exec_result)
                            # Para list_reminders, hablar el resultado ya que Gemini no lo hizo
                            if intent_result["intent"] == "list_reminders":
                                speak_text(exec_result)
                            # No hablar exec_result para otros, Gemini ya manejó la conversación
                except Exception as e:
                    print(f"[INTENT ERROR] {e}")
            else:
                print("Lo siento, no pude generar respuesta.")
                speak_text("Lo siento, no pude generar respuesta.")

        print("Conversación finalizada. Esperando palabra de activación...")
    def run(self):
        try:
            self.listener.start_listening()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nApagando a Aurora.")
            self.listener.stop_listening()

if __name__ == "__main__":
    aurora = Aurora()
    aurora.run()