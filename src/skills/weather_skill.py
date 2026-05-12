import requests
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")

def execute(command_text):
    if "clima" not in command_text and "temperatura" not in command_text:
        return None
    # Extraer ciudad (muy básico)
    words = command_text.split()
    ciudad = "Cali"  # por defecto
    for w in words:
        if w[0].isupper() and len(w) > 2:
            ciudad = w
            break
    url = f"http://api.openweathermap.org/data/2.5/weather?q={ciudad}&appid={API_KEY}&units=metric&lang=es"
    try:
        resp = requests.get(url)
        data = resp.json()
        if resp.status_code == 200:
            temp = data['main']['temp']
            desc = data['weather'][0]['description']
            return f"El clima en {ciudad} es {desc} con {temp} grados Celsius."
        else:
            return "No pude obtener el clima."
    except:
        return "Error al consultar el clima."