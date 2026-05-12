import asyncio
import os
import traceback
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from androidtvremote2 import AndroidTVRemote
import datetime

# Configuración
TV_IP = "192.168.1.12"
CERT_DIR = Path("config/certs")
CERT_FILE = CERT_DIR / "cert.pem"
KEY_FILE = CERT_DIR / "key.pem"

# Crear directorio de certificados si no existe
CERT_DIR.mkdir(parents=True, exist_ok=True)

def generate_certificates():
    """Genera certificados autofirmados si no existen"""
    if CERT_FILE.exists() and KEY_FILE.exists():
        print("✓ Certificados existentes encontrados")
        return True
    
    print("→ Generando certificados autofirmados...")
    
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
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Python_Control_TV"),
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
        with open(KEY_FILE, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Guardar certificado
        with open(CERT_FILE, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        print("✓ Certificados generados exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error generando certificados: {e}")
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
        print(f"⚠ Se corrigió el PIN de '{pin}' a '{corrected}' para emparejar.")
        return corrected
    except ValueError:
        return pin


    
async def main():
    if not generate_certificates():
        return

    remote = AndroidTVRemote(
        client_name="Python_Control_TV",
        certfile=str(CERT_FILE),
        keyfile=str(KEY_FILE),
        host=TV_IP
    )
    
    print(f"\nConectando a {TV_IP}...")
    
    try:
        # Intentar conectar
        await remote.async_connect()
        print("✓ ¡Conectado exitosamente!")
        
    except Exception as e:
        # Si fallaconnexión, probablemente necesita emparejamiento
        print(f"⚠ Error de conexión: {type(e).__name__}")
        print(f"   Detalles: {str(e)}\n")
        print("→ Iniciando proceso de emparejamiento...")
        print("⚠ MIRA TU TELEVISOR - Se mostrará un código PIN\n")
        
        try:
            # Iniciar emparejamiento
            print("→ Enviando solicitud de emparejamiento...")
            await remote.async_start_pairing()
            print("✓ Solicitud de emparejamiento enviada\n")
            
            # Pedir PIN al usuario
            raw_pin = input("Introduce el PIN que ves en tu TV: ").strip()
            
            if not raw_pin:
                print("❌ PIN no proporcionado")
                return

            pin = normalize_pairing_pin(raw_pin)
            if len(pin) != 6:
                print(f"❌ PIN inválido: '{raw_pin}' debe tener 6 caracteres hexadecimales")
                return

            # Validar PIN
            print("→ Validando PIN...")
            result = await remote.async_finish_pairing(pin)
            
            if result:
                print("✓ ¡Emparejamiento completado!")
                print("✓ Certificados guardados en config/certs/")
            else:
                print("❌ PIN incorrecto")
                return
                
        except Exception as pairing_error:
            print(f"❌ Error en emparejamiento: {type(pairing_error).__name__}")
            print(f"   Detalles: {str(pairing_error)}")
            print("\n🔍 DEBUGGING:")
            traceback.print_exc()
            return
    
    # Una vez conectado, enviar comandos
    print("\n" + "="*50)
    print("ENVIANDO COMANDOS DE DEMOSTRACIÓN")
    print("="*50 + "\n")
    
    try:
        # Lista de comandos a enviar
        comandos = [
            ("VOLUME_UP", "Subir volumen"),
            ("VOLUME_UP", "Subir volumen again"), 
            ("VOLUME_DOWN", "Bajar volumen"),
            ("HOME", "Ir a Inicio"),
        ]
        
        for cmd, desc in comandos:
            print(f"→ Enviando: {cmd} ({desc})")
            try:
                remote.send_key_command(cmd)
                print(f"   ✓ {cmd} enviado\n")
            except Exception as e:
                print(f"   ⚠ Error: {e}\n")
            
            await asyncio.sleep(1)
        
        print("✓ Demostración completada\n")
        
    except Exception as e:
        print(f"❌ Error durante demostración: {e}")
        traceback.print_exc()
    
    finally:
        # Desconectar
        try:
            await remote.async_disconnect()
            print("✓ Desconectado del TV")
        except:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠ Programa interrumpido por el usuario")
    except Exception as e:
        print(f"\n❌ Error general: {e}")
        traceback.print_exc()
