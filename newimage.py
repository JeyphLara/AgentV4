import requests
import json
import base64

import os

api_key = os.getenv("OPENROUTE_API_KEY")
if not api_key:
    raise RuntimeError("OPENROUTE_API_KEY no está definido en el entorno")

response = requests.post(
    url="https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    data=json.dumps({
        "model": "google/gemini-2.5-flash-image",
        "messages": [
            {
                "role": "user",
                "content": "Generate a beautiful sunset over mountains"
            }
        ]
    })
)

result = response.json()

print("DEBUG FULL RESPONSE:\n")
print(json.dumps(result, indent=2))

message = result["choices"][0]["message"]

# buscar imagen
if "images" in message:
    for img in message["images"]:
        b64 = img["image_url"]["url"]

        # quitar prefijo si existe
        if "base64," in b64:
            b64 = b64.split("base64,")[1]

        image_data = base64.b64decode(b64)

        with open("image.png", "wb") as f:
            f.write(image_data)

        print("Imagen guardada como image.png")