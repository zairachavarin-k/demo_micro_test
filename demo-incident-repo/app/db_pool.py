"""
Pool de conexiones simulado (en memoria).

No se necesita una base de datos real: un semáforo simula un pool de
conexiones de tamaño fijo, igual que haría PostgreSQL o SQLAlchemy.

El comportamiento cambia según la variable de entorno FAULT_MODE:
  - "none"      -> Comportamiento correcto: la conexión siempre se libera.
  - "pool_leak" -> BUG: la conexión no se libera (fuga), el pool se agota.

Esto permite desplegar la app en Azure con cero dependencias externas
(sin Docker, sin Postgres) y aun así reproducir un incidente real de
agotamiento de pool bajo carga concurrente.
"""

import os
import threading
import time

FAULT_MODE = os.getenv("FAULT_MODE", "none").lower()
POOL_SIZE = int(os.getenv("POOL_SIZE", "5"))

# El semáforo actúa como el "pool": solo POOL_SIZE conexiones a la vez.
_pool = threading.Semaphore(POOL_SIZE)


class Conexion:
    """Representa una conexión tomada del pool."""

    def __init__(self):
        self._liberada = False

    def liberar(self):
        """Devuelve la conexión al pool. Debe llamarse siempre."""
        if not self._liberada:
            _pool.release()
            # Mantener contador de conexiones activas coherente.
            with _active_lock:
                global _active_count
                if _active_count > 0:
                    _active_count -= 1
            self._liberada = True


def obtener_conexion(timeout=3.0):
    """
    Toma una conexión del pool. Si no hay ninguna libre en `timeout`
    segundos, lanza TimeoutError (igual que un pool real agotado).
    """
    adquirida = _pool.acquire(timeout=timeout)
    if not adquirida:
        raise TimeoutError(
            "No hay conexiones disponibles en el pool "
            f"(tamaño={POOL_SIZE}). Posible fuga de conexiones."
        )
    # Registrar una conexión activa (para evidencia/diagnóstico).
    with _active_lock:
        global _active_count
        _active_count += 1
    return Conexion()


def ejecutar_consulta_simulada(datos):
    """
    Simula una consulta a base de datos usando el pool.

    En modo sano, la conexión SIEMPRE se libera (bloque finally).
    En modo 'pool_leak', se omite la liberación a propósito: cada
    llamada se queda con su conexión, el pool se vacía, y las
    siguientes llamadas esperan hasta el timeout.
    """
    conexion = obtener_conexion()
    try:
        # Simula el trabajo de la consulta.
        time.sleep(0.05)
        resultado = {"procesado": True, "items": len(datos)}
        return resultado
    finally:
        if FAULT_MODE == "pool_leak":
            # BUG INTENCIONAL: no liberamos la conexión.
            # En modo de fuga dejamos _active_count sin decrementar para
            # que refleje la fuga de conexiones (evidencia).
            pass
        else:
            conexion.liberar()


# Instrumentación mínima para recopilación de evidencia
_active_count = 0
_active_lock = threading.Lock()


def get_pool_metrics():
    """Devuelve métricas/estado del pool para evidencia de degradación.

    Retorna un diccionario con: pool_size, active_connections,
    available_permits (estimate), y el modo de fallo activo.
    """
    with _active_lock:
        active = _active_count

    # threading.Semaphore no expone el contador públicamente; estimar
    # disponibles como POOL_SIZE - active para esta demo.
    available = max(0, POOL_SIZE - active)

    return {
        "pool_size": POOL_SIZE,
        "active_connections": active,
        "available_permits_estimate": available,
        "fault_mode": FAULT_MODE,
    }
