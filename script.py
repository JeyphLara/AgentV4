import asyncio
import io
import os
import sys
import traceback
import argparse
import cv2
import pyaudio
import PIL.Image
import mss

from google import genai
from google.genai import types

# Compatibilidad para versiones de Python anteriores a 3.11
if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup
    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

# --- Configuración de Audio ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

# --- Configuración del Modelo ---
# Nota: "gemini-2.0-flash-exp" es el modelo actual para Live. 
# Si usas uno anterior, asegúrate de que sea compatible con Live.
MODEL = "models/gemini-3.1-flash-live-preview" 
DEFAULT_MODE = "camera"

# REEMPLAZA ESTO CON TU NUEVA CLAVE
client = genai.Client(
    api_key="AIzaSyDs8bIsC-whnb1PswRnkg3hFEE_gkny1Hw",
    http_options={"api_version": "v1beta"},
)

CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
        )
    ),
)

pya = pyaudio.PyAudio()

class AudioVideoLoop:
    def __init__(self, video_mode=DEFAULT_MODE):
        self.video_mode = video_mode
        self.audio_in_queue = asyncio.Queue()
        self.out_queue = asyncio.Queue(maxsize=5)
        self.session = None

    # --- Audio Handling ---

    async def listen_audio(self):
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=CHUNK_SIZE,
        )
        
        kwargs = {"exception_on_overflow": False} if __debug__ else {}
        
        try:
            while True:
                data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
                # Objeto Blob para el audio
                payload = types.Blob(
                    mime_type="audio/pcm",
                    data=data
                )
                try:
                    self.out_queue.put_nowait(payload)
                except asyncio.QueueFull:
                    _ = self.out_queue.get_nowait()  
                    self.out_queue.put_nowait(payload)
        except asyncio.CancelledError:
            pass
        finally:
            self.audio_stream.stop_stream()
            self.audio_stream.close()

    async def play_audio(self):
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        try:
            while True:
                bytestream = await self.audio_in_queue.get()
                await asyncio.to_thread(stream.write, bytestream)
        except asyncio.CancelledError:
            pass
        finally:
            stream.stop_stream()
            stream.close()

    async def receive_audio(self):
        try:
            while True:
                turn = self.session.receive()
                async for response in turn:
                    if data := response.data:
                        self.audio_in_queue.put_nowait(data)
                        continue
                    if text := response.text:
                        print(f"\nGemini: {text}")

                # Limpiar audio si el usuario interrumpe
                while not self.audio_in_queue.empty():
                    self.audio_in_queue.get_nowait()
        except asyncio.CancelledError:
            pass

    # --- Video Handling ---

    def _capture_frame(self, cap):
        ret, frame = cap.read()
        if not ret:
            return None
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(frame_rgb)
        img.thumbnail([1024, 1024])

        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        
        return types.Blob(
            mime_type="image/jpeg",
            data=image_io.getvalue()
        )

    async def capture_frames(self):
        cap = await asyncio.to_thread(cv2.VideoCapture, 0)
        try:
            while True:
                blob = await asyncio.to_thread(self._capture_frame, cap)
                if blob is None:
                    break
                await asyncio.sleep(1.0)
                await self.out_queue.put(blob)
        except asyncio.CancelledError:
            pass
        finally:
            cap.release()

    def _capture_screen(self):
        sct = mss.mss()
        monitor = sct.monitors[0] # Ajusta según tu monitor
        i = sct.grab(monitor)
        img = PIL.Image.frombytes("RGB", i.size, i.rgb)
        img.thumbnail([1024, 1024])

        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        
        return types.Blob(
            mime_type="image/jpeg",
            data=image_io.getvalue()
        )

    async def capture_screen(self):
        try:
            while True:
                blob = await asyncio.to_thread(self._capture_screen)
                await asyncio.sleep(1.0)
                await self.out_queue.put(blob)
        except asyncio.CancelledError:
            pass

    # --- Communication ---

    async def send_realtime(self):
        try:
            while True:
                item = await self.out_queue.get()
                # CAMBIO CLAVE: Sin corchetes [] y usando audio/video
                if item.mime_type.startswith("audio/"):
                    await self.session.send_realtime_input(audio=item)
                else:
                    # Las imágenes en flujo continuo se envían como 'video'
                    await self.session.send_realtime_input(video=item)
        except asyncio.CancelledError:
            pass

    async def send_text(self):
        try:
            while True:
                text = await asyncio.to_thread(input, "Tú > ")
                if text.strip().lower() == "q":
                    break
                await self.session.send_client_content(
                    turns=[types.Content(parts=[types.Part(text=text)])],
                    turn_complete=True,
                )
        except asyncio.CancelledError:
            pass

    async def run(self):
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session

                tg.create_task(self.listen_audio())
                tg.create_task(self.send_realtime())
                tg.create_task(self.receive_audio())
                tg.create_task(self.play_audio())
                
                if self.video_mode == "camera":
                    tg.create_task(self.capture_frames())
                elif self.video_mode == "screen":
                    tg.create_task(self.capture_screen())

                print("--- Conexión establecida. Escribe 'q' para salir ---")
                await self.send_text()
                raise asyncio.CancelledError()

        except asyncio.CancelledError:
            print("\nSesión finalizada.")
        except Exception:
            traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_MODE,
        choices=["camera", "screen", "none"],
    )
    args = parser.parse_args()
    main = AudioVideoLoop(video_mode=args.mode)
    asyncio.run(main.run())