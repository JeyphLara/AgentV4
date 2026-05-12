import asyncio
import os
import re
import unicodedata
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from androidtvremote2 import AndroidTVRemote
import datetime
from concurrent.futures import ThreadPoolExecutor
import shutil

# Mapeo de apps disponibles
APPS = {
    "youtube": "com.google.android.youtube.tv",
    "youtube music": "com.google.android.youtube.tv",
    "netflix": "com.netflix.ninja",
    "prime": "com.amazon.amazonvideo.livingroom",
    "prime video": "com.amazon.amazonvideo.livingroom",
    "spotify": "com.spotify.tv.android",
    "disney": "com.disney.disneyplus",
    "disney plus": "com.disney.disneyplus",
}

def _normalize_command(text: str) -> str:
    """Normaliza texto para parsing atenuando acentos y mayúsculas."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("ASCII")
    return text.lower()

def _get_cert_dir(tv_ip):
    """Obtiene el directorio de certificados para un TV específico"""
    cert_dir = Path("config/certs") / tv_ip.replace(":", "_")
    cert_dir.mkdir(parents=True, exist_ok=True)
    return cert_dir

def _delete_certificates(cert_dir):
    """Elimina certificados existentes para re-emparejar"""
    try:
        if cert_dir.exists():
            shutil.rmtree(cert_dir)
            print(f"[TV_SKILL] Certificados eliminados: {cert_dir}")
            # Recrear directorio
            cert_dir.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        print(f"[TV_SKILL ERROR] Eliminando certificados: {e}")
        return False

def normalize_pairing_pin(pin: str) -> str:
    """Normaliza el PIN para el emparejamiento.

    El TV puede mostrar caracteres que parecen hex, como O en lugar de 0.
    Aquí convertimos los más comunes y devolvemos la versión corregida.
    """
    pin = pin.strip().upper()
    if len(pin) != 6:
        return pin

    try:
        bytes.fromhex(pin)
        return pin
    except ValueError:
        pass

    translation = str.maketrans({
        "O": "0",
        "I": "1",
        "L": "1",
        "S": "5",
        "B": "8",
        "Z": "2",
    })
    corrected = pin.translate(translation)
    try:
        bytes.fromhex(corrected)
        print(f"[TV_SKILL] Se corrigió el PIN de '{pin}' a '{corrected}' para emparejar.")
        return corrected
    except ValueError:
        return pin


def _normalize_command(text: str) -> str:
    """Normaliza texto para facilitar el parsing de comandos."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = normalized.encode("ASCII", "ignore").decode("ASCII")
    return normalized.lower()


def _safe_disconnect(remote):
    """Desconecta el remote si está conectado."""
    try:
        if remote:
            remote.disconnect()
    except Exception:
        pass


def _generate_certificates(cert_dir):
    """Genera certificados autofirmados si no existen"""
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"

    if cert_file.exists() and key_file.exists():
        return str(cert_file), str(key_file)

    try:
        # Generar clave privada
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Generar certificado autofirmado
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"State"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, u"City"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Aurora_TV_Control"),
            x509.NameAttribute(NameOID.COMMON_NAME, u"android-tv"),
        ])

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([x509.DNSName(u"*")]),
            critical=False,
        ).sign(private_key, hashes.SHA256())

        # Guardar clave privada
        with open(key_file, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))

        # Guardar certificado
        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        return str(cert_file), str(key_file)
    except Exception as e:
        print(f"[TV_SKILL ERROR] Generando certificados: {e}")
        return None, None

async def _pair_with_tv(tv_ip, certfile, keyfile):
    """Intenta emparejar con el TV de forma interactiva siguiendo el patrón de controltv.py"""
    try:
        print(f"\n[TV_SKILL] Iniciando pairing con TV en {tv_ip}")
        print("⚠ MIRA TU TELEVISOR - Se mostrará un código PIN")

        remote = AndroidTVRemote(
            client_name="Aurora_TV_Control",
            certfile=certfile,
            keyfile=keyfile,
            host=tv_ip
        )

        # Iniciar emparejamiento
        print("→ Enviando solicitud de emparejamiento...")
        await remote.async_start_pairing()
        print("✓ Solicitud de emparejamiento enviada")

        # Pedir PIN al usuario
        raw_pin = input("Introduce el PIN que ves en tu TV: ").strip()

        if not raw_pin:
            return None, "PIN no proporcionado"

        pin = normalize_pairing_pin(raw_pin)
        if len(pin) != 6:
            return None, f"PIN inválido: '{raw_pin}' debe tener 6 caracteres hexadecimales"

        # Validar PIN
        print("→ Validando PIN...")
        result = await remote.async_finish_pairing(pin)

        if result:
            print("✓ ¡Emparejamiento completado!")
            print("✓ Certificados guardados")
            return remote, None
        else:
            return None, "PIN incorrecto"

    except Exception as e:
        return None, f"Error en emparejamiento: {str(e)}"
async def _send_command_async(tv_ip, certfile, keyfile, command, cert_dir=None):
    """Envía un comando al TV de forma asíncrona, con manejo de pairing"""
    try:
        remote = AndroidTVRemote(
            client_name="Aurora_TV_Control",
            certfile=certfile,
            keyfile=keyfile,
            host=tv_ip
        )

        try:
            await remote.async_connect()
        except Exception as e:
            error_msg = str(e)
            # Si el error es de pairing, intentar re-emparejar
            if "pair" in error_msg.lower() or "need to pair" in error_msg.lower():
                print(f"\n[TV_SKILL] Error de pairing detectado")

                # Eliminar certificados antiguos
                if cert_dir:
                    _delete_certificates(cert_dir)
                    # Regenerar certificados
                    certfile, keyfile = _generate_certificates(cert_dir)

                # Intentar pairing nuevo
                _, pair_error = await _pair_with_tv(tv_ip, certfile, keyfile)
                if pair_error:
                    return pair_error

                # Recrear conexión con nuevos certificados
                remote = AndroidTVRemote(
                    client_name="Aurora_TV_Control",
                    certfile=certfile,
                    keyfile=keyfile,
                    host=tv_ip
                )

                try:
                    await remote.async_connect()
                except Exception as retry_err:
                    return f"Error después del pairing: {str(retry_err)}"
            else:
                raise

        # Procesar comando
        command_lower = _normalize_command(command)

        # Encendido / apagado
        if re.search(r'\b(enciende|encienda|prende|prender|on)\b', command_lower):
            remote.send_key_command("POWER")
            _safe_disconnect(remote)
            return "Encendiendo el TV"
        if re.search(r'\b(apaga|apagalo|apágalo|apagar|off)\b', command_lower):
            remote.send_key_command("POWER")
            _safe_disconnect(remote)
            return "Apagando el TV"

        # Buscar porcentaje de volumen absoluto antes de los cambios simples
        if 'volumen' in command_lower or 'vol' in command_lower:
            percent_match = re.search(r'volumen.*?(\d+)\s*(?:%|por ciento|porciento)?|al\s+(\d+)\s*(?:%|por ciento|porciento)?|\b(\d+)\s*(?:%|por ciento|porciento)\b', command_lower)
            if percent_match:
                percentage = next(int(x) for x in percent_match.groups() if x and x.isdigit())
                percentage = max(0, min(100, percentage))
                
                # Intentar set absoluto usando volume_info
                try:
                    vol_info = remote.volume_info
                    if vol_info and 'level' in vol_info and 'max_level' in vol_info:
                        current = vol_info['level']
                        max_vol = vol_info['max_level']
                        target = int(percentage / 100 * max_vol)
                        if target > current:
                            steps = target - current
                            key = "VOLUME_UP"
                        elif target < current:
                            steps = current - target
                            key = "VOLUME_DOWN"
                        else:
                            steps = 0
                        for _ in range(steps):
                            remote.send_key_command(key)
                            await asyncio.sleep(0.1)
                        _safe_disconnect(remote)
                        return f"Volumen establecido a {percentage}% (nivel {target}/{max_vol})"
                except Exception as vol_err:
                    print(f"[TV_SKILL] Error leyendo volume_info: {vol_err}")
                
                # Fallback a aproximación
                steps = max(1, int(percentage / 6.67))
                for _ in range(steps):
                    remote.send_key_command("VOLUME_UP")
                    await asyncio.sleep(0.1)
                _safe_disconnect(remote)
                return f"Volumen establecido aproximadamente a {percentage}%"

        # Abrir app
        app_match = re.search(r'\b(abre|abrir|pon|inicia|lanza|ejecuta)\b.*\b(' + '|'.join(re.escape(k) for k in APPS.keys()) + r')\b', command_lower)
        if app_match:
            app_name = app_match.group(2).strip()
            if app_name in APPS:
                package_name = APPS[app_name]
                try:
                    remote.send_launch_app_command(package_name)
                    _safe_disconnect(remote)
                    return f"Abriendo {app_name} en el TV"
                except Exception as launch_err:
                    _safe_disconnect(remote)
                    return f"Error abriendo {app_name}: {launch_err}"
            _safe_disconnect(remote)
            return f"App '{app_name}' no reconocida"

        # Buscar en app
        search_match = re.search(r'\b(busca|reproduce|pon|encuentra)\b\s+(.+?)\s+en\s+(' + '|'.join(re.escape(k) for k in APPS.keys()) + r')\b', command_lower)
        if search_match:
            query = search_match.group(2).strip()
            app_name = search_match.group(3).strip()
            if app_name in APPS:
                package_name = APPS[app_name]
                try:
                    remote.send_launch_app_command(package_name)
                    await asyncio.sleep(4)
                    remote.send_key_command("SEARCH")
                    await asyncio.sleep(1)
                    remote.send_text(query)
                    await asyncio.sleep(0.5)
                    remote.send_key_command("ENTER")
                    _safe_disconnect(remote)
                    return f"Buscando '{query}' en {app_name}"
                except Exception as launch_err:
                    _safe_disconnect(remote)
                    return f"Error buscando en {app_name}: {launch_err}"
            _safe_disconnect(remote)
            return f"App '{app_name}' no reconocida"

        # Controles de reproducción y volumen
        if re.search(r'\b(sube|subele|súbele|aumenta|eleva|incrementa|más)\b.*\b(volumen|vol)\b', command_lower):
            remote.send_key_command("VOLUME_UP")
            _safe_disconnect(remote)
            return "Volumen aumentado"
        elif re.search(r'\b(baja|disminuye|reduce|menos|disminuye)\b.*\b(volumen|vol)\b', command_lower):
            remote.send_key_command("VOLUME_DOWN")
            _safe_disconnect(remote)
            return "Volumen reducido"

        if re.search(r'\b(mute|silenciar)\b', command_lower):
            remote.send_key_command("MUTE")
            _safe_disconnect(remote)
            return "TV muteado"
        if re.search(r'\b(home|inicio|principal)\b', command_lower):
            remote.send_key_command("HOME")
            _safe_disconnect(remote)
            return "Volviendo al inicio"
        if re.search(r'\b(atras|atrás|back)\b', command_lower):
            remote.send_key_command("BACK")
            _safe_disconnect(remote)
            return "Atrás"
        if re.search(r'\b(play|reproducir|pausar|pause)\b', command_lower) and 'pausa' not in command_lower:
            remote.send_key_command("PLAY_PAUSE")
            _safe_disconnect(remote)
            return "Play/Pausa enviado"
        if re.search(r'\b(pausa|pause)\b', command_lower):
            remote.send_key_command("PAUSE")
            _safe_disconnect(remote)
            return "Pausa enviada"
        if re.search(r'\b(stop|detener|parar)\b', command_lower):
            remote.send_key_command("STOP")
            _safe_disconnect(remote)
            return "Detenido"

        _safe_disconnect(remote)
        return f"Comando no reconocido: '{command}'"

    except Exception as e:
        return f"Error en TV: {str(e)}"

def execute(device_info, action):
    """
    Interfaz sincrónica para ejecutar comandos en el TV.
    Mantiene compatibilidad con el código existente.
    Maneja tanto event loops existentes como la creación de nuevos.
    """
    print(f"[DEBUG] tv_skill: device={device_info}, action='{action}'")

    tv_ip = device_info.get('ip')
    if not tv_ip:
        return "No tengo la IP del TV."

    # Generar/obtener certificados
    cert_dir = _get_cert_dir(tv_ip)
    cert_file, key_file = _generate_certificates(cert_dir)

    if not cert_file or not key_file:
        return "Error generando certificados para el TV."

    # Ejecutar comando de forma síncrona
    try:
        # Verificar si ya hay un event loop corriendo
        try:
            existing_loop = asyncio.get_running_loop()
            # Si hay loop corriendo (ej: Gemini Live), ejecutar en thread separado
            with ThreadPoolExecutor() as executor:
                # Crear nuevo loop en el thread
                def run_async_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_send_command_async(tv_ip, cert_file, key_file, action, cert_dir))
                    finally:
                        new_loop.close()

                result = executor.submit(run_async_in_thread).result(timeout=60)
                return result
        except RuntimeError:
            # No hay loop corriendo, crear uno nuevo
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(_send_command_async(tv_ip, cert_file, key_file, action, cert_dir))
                return result
            finally:
                loop.close()
    except Exception as e:
        return f"Error ejecutando comando en TV: {str(e)}"