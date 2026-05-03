"""conftest.py — Configuración global de pytest.

Instala automáticamente los stubs de hardware antes de cualquier test,
para que los módulos que dependen de serial/smbus2 puedan importarse
sin necesitar una Raspberry Pi conectada.
"""

import sys
import os

# Añadir src/ al path para que los tests puedan importar módulos directamente
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Instalar stubs de hardware
from stubs.hardware_stubs import install as install_hw_stubs
install_hw_stubs()
