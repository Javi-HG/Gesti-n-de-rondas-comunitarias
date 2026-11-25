"""Script de verificación local antes de hacer push: estilo (flake8) y pruebas (pytest).

Uso:  python verifica.py
La configuración de ambas herramientas está en setup.cfg.
"""

import subprocess
import sys


def ejecutar(comando: list[str]) -> int:
    print(f"\n>>> Ejecutando: {' '.join(comando)}")
    return subprocess.run(comando).returncode


def main() -> int:
    codigo_flake8 = ejecutar([sys.executable, "-m", "flake8", "."])
    codigo_pytest = ejecutar([sys.executable, "-m", "pytest", "-v"])

    if codigo_flake8 == 0 and codigo_pytest == 0:
        print("\n[OK] TODO EN VERDE: estilo y pruebas aprobadas. Listo para git push.")
        return 0
    print("\n[ERROR] Revisa los fallos antes de subir el código.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
