# src/core/wake_word_listener.py
import speech_recognition as sr
import threading
import time
import queue
from resemblyzer import VoiceEncoder
import numpy as np

class WakeWordListener:
    """
    Detector de palabra de activación que corre en un hilo separado.
    Cada ciclo de escucha abre y cierra el micrófono correctamente.
    """

    def __init__(self, wake_word, on_activation):
        self.wake_word = wake_word.lower()
        self.on_activation_callback = on_activation
        self.recognizer = sr.Recognizer()
        self.is_listening = False
        self.thread = None
        # Ajusta el nivel de energía mínimo para detección (reduce ruido)
        self.recognizer.energy_threshold = 300
        # Pequeña pausa para adaptarse al ruido ambiente
        self.recognizer.dynamic_energy_threshold = True
        # Modelo de speaker embedding
        self.encoder = VoiceEncoder()

    def start_listening(self):
        """Inicia el hilo de escucha."""
        if self.is_listening:
            return
        self.is_listening = True
        self.thread = threading.Thread(target=self._listen_loop)
        self.thread.daemon = True   # El hilo se cierra cuando el principal termina
        self.thread.start()

    def stop_listening(self):
        """Detiene el hilo de escucha."""
        self.is_listening = False
        if self.thread and self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)

    def _listen_loop(self):
        """Bucle principal que escucha la palabra de activación."""
        # Usamos un microfono por defecto
        mic = sr.Microphone()

        # Ajuste inicial para ruido de fondo (solo una vez)
        with mic as source:
            print("Ajustando sensibilidad al ruido ambiente...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            print("Ajuste completado. Escuchando palabra '{}'...".format(self.wake_word))

        while self.is_listening:
            try:
                # Cada iteración abre y cierra el micrófono correctamente
                with mic as source:
                    # Escucha durante 2 segundos como máximo, frases de hasta 4 segundos
                    audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=4)
                
                # Procesar el audio fuera del contexto 'with' para liberar rápido el micrófono
                text = self.recognizer.recognize_google(audio, language="es-ES").lower()
                
                if self.wake_word in text:
                    print(f"\n🔊 Palabra de activación '{self.wake_word}' detectada.")
                    # Llamar al callback (esto ejecuta la conversación)
                    self.on_activation_callback()
                    # Pequeña pausa para evitar múltiples activaciones seguidas
                    time.sleep(1.5)

            except sr.WaitTimeoutError:
                # No se detectó audio en el tiempo de espera, es normal
                continue
            except sr.UnknownValueError:
                # No se entendió lo que se dijo, ignorar
                continue
            except OSError as e:
                # Error de hardware o permisos del micrófono
                print(f"Error de hardware de audio: {e}")
                time.sleep(2)
            except Exception as e:
                # Cualquier otro error, mostrarlo una vez y seguir
                print(f"Error inesperado en bucle de escucha: {e}")
                time.sleep(1)

    async def capture_command(self):
        """
        Captura el comando completo del usuario después de la activación.
        Se ejecuta en el hilo principal (asíncrono).
        """
        mic = sr.Microphone()
        # Crear un nuevo recognizer para evitar conflictos
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = self.recognizer.energy_threshold
        recognizer.dynamic_energy_threshold = self.recognizer.dynamic_energy_threshold
        with mic as source:
            print("🎤 Escuchando tu solicitud...")
            # Ajuste rápido para el ruido justo antes de grabar
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                # Escucha hasta 15 segundos para el comando (aumentado)
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=15)
                text = recognizer.recognize_google(audio, language="es-ES")
                
                # Extraer embedding de voz
                raw_data = audio.get_raw_data()
                waveform = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
                embedding = self.encoder.embed_utterance(waveform)
                embedding = embedding.tolist()
                
                return text, embedding
            except sr.WaitTimeoutError:
                print("No detecté ninguna solicitud.")
                return None, None
            except sr.UnknownValueError:
                print("No pude entender lo que dijiste.")
                return None, None