"""Migracion vacia que sostiene el grafo.

`core/0019_merge_20260426_0348` la declara como dependencia, pero el archivo
nunca se commiteo: vivia suelto en el servidor y `deploy.sh` la borraba antes
de cada `git pull` para evitar conflictos, recreandola despues.

El efecto era que **un clon nuevo del repositorio no podia correr migraciones**:
`manage.py migrate` reventaba con NodeNotFoundError apuntando a este archivo.
Se descubrio el 24-ago-2026 preparando la entrega, escribiendo el README:
el primer comando del arranque rapido fallaba.

No hace nada (`operations = []`) y no puede hacer nada: solo existe para que
la 0019 tenga un padre. Commitearla vuelve inerte el parche del deploy, que
solo borra el archivo si NO esta trackeado.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_cronheartbeat'),
    ]

    operations = []
