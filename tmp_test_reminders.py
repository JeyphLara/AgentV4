from src.skills.reminders_skill import execute

texts = [
    'quiero que me recuerdes dentro de 2 minutos ir a la cocina',
    'recuérdame ir a la cocina en 2 minutes',
    'recuérdame media hora para llamar a mamá',
    'recuérdame a las 1:00pm ir a la tienda',
    'recuérdame el 27 de mayo a las 2:00pm ir al gimnasio',
    'recuérdame en dos horas revisar el correo'
]

for text in texts:
    print('INPUT:', text)
    print('OUTPUT:', execute('yo', text))
    print('---')
