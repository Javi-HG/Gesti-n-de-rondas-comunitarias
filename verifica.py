"""Script de verificación local antes de hacer push (Clase 15)."""

import subprocess
import sys


def ejecutar(comando: list[str]) -> int:
    print(f"\n>>> Ejecutando: {' '.join(comando)}")
    resultado = subprocess.run(comando)
    return resultado.returncode


if __name__ == "__main__":
    codigo_flake8 = ejecutar([sys.executable, "-m", "flake8", "src", "tests", "--max-line-length=95"])
    codigo_pytest = ejecutar([sys.executable, "-m", "pytest", "-v"])

    if codigo_flake8 == 0 and codigo_pytest == 0:
        print("\n[OK] TODO EN VERDE: Estilo y pruebas aprobadas. Listo para git push.")
        sys.exit(0)
    else:
        print("\n[ERROR] Revisa los fallos antes de subir el código.")
        sys.exit(1)


codigo_flake8 = ejecutar([sys.executable, "-m", "flake8", ".", "--max-line-length=95"])