"""
Paginacion estandar para todos los endpoints DRF de Pulstock.

Cambio respecto al default de DRF:
- Habilita `page_size_query_param = "page_size"`. Antes el cliente no
  podia pedir mas resultados aunque enviara `?page_size=N`.
  Daniel reporto: la lista de productos en /recetas solo mostraba 50
  aunque el frontend pedia 200.
- max_page_size = 500: tope razonable para evitar que un cliente
  pida toda la base de un golpe (DoS por accidente).
"""
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 50  # default si el cliente no especifica
    page_size_query_param = "page_size"
    max_page_size = 500
