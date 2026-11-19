"""
h3-indexing - biblioteca para agregação de camadas vetoriais em grade hexagonal H3.

Transforma camadas de polígonos (bairros, distritos, municípios, setores
censitários etc.) em uma grade hexagonal H3 padronizada, redistribuindo
atributos numéricos originais para os hexágonos gerados.
"""

from .distribution import AttributeType

__all__ = ["AttributeType"]
__version__ = "0.1.0"