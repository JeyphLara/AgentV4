import json
import re
from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

class IntentDetector:
    """Detecta intenciones analizando la respuesta de Gemini"""

    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_client = genai.Client(api_key=self.gemini_api_key) if self.gemini_api_key else None

    def extract_intent_from_response(self, response_text: str) -> dict:
        """
        Extrae intención de una respuesta que contiene JSON embebido.
        Formato esperado: "Texto conversacional... [INTENT_JSON]{"intent": "...", "params": {...}}[/INTENT_JSON]"
        
        Returns:
            {"intent": "...", "params": {...}, "message": "texto conversacional"}
        """
        try:
            # Buscar JSON embebido entre marcadores
            pattern = r'\[INTENT_JSON\](.*?)\[/INTENT_JSON\]'
            match = re.search(pattern, response_text, re.DOTALL)
            
            if match:
                json_str = match.group(1).strip()
                intent_data = json.loads(json_str)
                
                # Extraer mensaje limpio (sin marcadores JSON)
                message = re.sub(pattern, '', response_text, flags=re.DOTALL).strip()
                if not message:
                    message = response_text.strip()
                
                return {
                    "intent": intent_data.get("intent", "none"),
                    "params": intent_data.get("params", {}),
                    "confidence": intent_data.get("confidence", 0.0),
                    "message": message
                }
        except Exception as e:
            print(f"[INTENT PARSE ERROR] {e}")

        # Sin intención detectada
        return {
            "intent": "none",
            "params": {},
            "confidence": 0.0,
            "message": response_text
        }

