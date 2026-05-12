import importlib
import json
import os
import re
import sys
import difflib

class SkillManager:
    def __init__(self):
        self.skills = {}
        self.devices = self.load_devices()
        self.load_skills()
        # Lista de nombres de dispositivos para búsqueda difusa
        self.device_names = list(self.devices.keys())
        print(f"[DEBUG] Skills cargados: {list(self.skills.keys())}")
        print(f"[DEBUG] Dispositivos: {self.device_names}")

    def _normalize(self, text):
        return re.sub(r"[^a-z0-9áéíóúñ ]", "", text.lower())

    def _expand_device_aliases(self, device_name):
        synonyms = {
            'tv': 'televisor',
            'televisor': 'tv',
            'lámpara': 'lampara',
            'lampara': 'lámpara'
        }

        parts = device_name.split()
        aliases = set([device_name])

        for p in parts:
            if p in synonyms:
                aliases.add(synonyms[p])

        if 'tv' in device_name and 'televisor' not in device_name:
            aliases.add(device_name.replace('tv', 'televisor'))
        if 'televisor' in device_name and 'tv' not in device_name:
            aliases.add(device_name.replace('televisor', 'tv'))

        # Añadir cada palabra individualmente para poder coincidir con comandos más cortos
        for part in parts:
            if part:
                aliases.add(part)
                if part in synonyms:
                    aliases.add(synonyms[part])

        return [self._normalize(a) for a in aliases]

    def _find_best_device(self, command_text):
        command_low = self._normalize(command_text)

        # 1. Coincidencia directa de nombre
        for device_name in self.device_names:
            if self._normalize(device_name) in command_low:
                return device_name

        # 2. Coincidencia por partes (incluyendo sinónimos)
        for device_name in self.device_names:
            aliases = self._expand_device_aliases(device_name)
            if all(part in command_low for part in self._normalize(device_name).split()):
                return device_name
            for alias in aliases:
                if alias in command_low:
                    return device_name

        # 3. Coincidencia difusa con levenshtein de palabras clave
        matches = difflib.get_close_matches(command_low, [self._normalize(n) for n in self.device_names], n=1, cutoff=0.5)
        if matches:
            normalized_match = matches[0]
            for device_name in self.device_names:
                if self._normalize(device_name) == normalized_match:
                    return device_name

        # 4. Si se menciona un tipo y solo hay un dispositivo de ese tipo, usarlo
        if 'tv' in command_low or 'televisor' in command_low:
            tv_devices = [name for name, info in self.devices.items() if info.get('type') == 'tv']
            if len(tv_devices) == 1:
                return tv_devices[0]

        if 'luz' in command_low or 'lampara' in command_low or 'lámpara' in command_low:
            light_devices = [name for name, info in self.devices.items() if info.get('type') == 'light']
            if len(light_devices) == 1:
                return light_devices[0]

        return None

    def _extract_action(self, command_text, device_name):
        command_low = self._normalize(command_text)
        device_low = self._normalize(device_name)
        action_low = command_low

        # Eliminar mención directa del dispositivo, sinónimos y preposiciones comunes
        tokens_to_remove = set(device_low.split())
        tokens_to_remove.update(self._expand_device_aliases(device_name))

        for token in sorted(tokens_to_remove, key=len, reverse=True):
            action_low = re.sub(rf"\b{re.escape(token)}\b", "", action_low)

        action_low = re.sub(r"\b(de|del|la|el|los|las|para|de la|del)\b", "", action_low)
        action_low = re.sub(r"\s+", " ", action_low).strip()

        if action_low:
            return action_low
        return ""

    def load_devices(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'devices.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def load_skills(self):
        skills_dir = os.path.join(os.path.dirname(__file__), '..', 'skills')
        sys.path.insert(0, os.path.dirname(skills_dir))
        for file in os.listdir(skills_dir):
            if file.endswith('_skill.py'):
                module_name = file[:-3]
                module = importlib.import_module(f'src.skills.{module_name}')
                self.skills[module_name] = module

    def handle(self, user_name, command_text):
        command_lower = command_text.lower()
        print(f"[DEBUG] SkillManager.handle: '{command_lower}'")

        # 1. Buscar dispositivo por coincidencia aproximada
        best_match = self._find_best_device(command_text)

        if best_match:
            device_info = self.devices[best_match]
            action = self._extract_action(command_text, best_match)
            if not action:
                # Si no hay acción extraída, usa texto completo para casar comandos como 'sube volumen'
                action = command_text

            print(f"[DEBUG] Dispositivo encontrado: {best_match}, acción='{action}'")
            skill_name = device_info['type'] + '_skill'
            if skill_name in self.skills:
                result = self.skills[skill_name].execute(device_info, action)
                if result:
                    return result
            else:
                print(f"[DEBUG] Skill {skill_name} no encontrado")

        # 2. Otros skills (recordatorios, clima)
        for skill_name, module in self.skills.items():
            if skill_name == 'reminders_skill':
                res = module.execute(user_name, command_text)
                if res:
                    return res
            elif skill_name == 'weather_skill':
                res = module.execute(command_text)
                if res:
                    return res

        print("[DEBUG] Ningún skill manejó el comando")
        return None