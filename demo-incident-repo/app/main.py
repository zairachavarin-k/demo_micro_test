"""
Servicio de Transacciones — API de ejemplo para la demo de incidentes.

Simula un servicio de procesamiento de pagos. Bajo FAULT_MODE=pool_leak,
se degrada con latencia alta y errores bajo carga concurrente,
reproduciendo un incidente de agotamiento del pool de conexiones.
"""

import time
from fastapi import FastAPI, HTTPException

from app.db_pool import ejecutar_consulta_simulada, FAULT_MODE

app = FastAPI(
    title="Servicio de Transacciones",
    description="API de procesamiento de pagos (demo de incidentes)",
    version="1.0.0",
)

# Datos de ejemplo en memoria.
_transacciones = [
    {"id": i, "monto": round(10.0 + i * 3.5, 2), "estado": "completado"}
    for i in range(1, 51)
]


@app.get("/")
def root():
    """Endpoint de bienvenida. Muestra el modo de fallo activo."""
    return {
        "servicio": "Servicio de Transacciones",
        "estado": "online",
        "fault_mode": FAULT_MODE,
    }


@app.get("/health")
def health():
    """Endpoint de salud para monitoreo (Azure Monitor lo puede usar)."""
    return {"status": "healthy"}


@app.get("/transactions")
def listar_transacciones():
    """
    Lista las transacciones. Este es el endpoint que se degrada
    cuando el pool de conexiones se agota.
    """
    inicio = time.time()
    try:
        resultado = ejecutar_consulta_simulada(_transacciones)
    except TimeoutError as e:
        raise HTTPException(status_code=503, detail=str(e))
    elapsed_ms = round((time.time() - inicio) * 1000, 1)
    return {
        "count": resultado["items"],
        "elapsed_ms": elapsed_ms,
        "transactions": _transacciones[:20],
    }


@app.get("/transactions/{transaction_id}")
def obtener_transaccion(transaction_id: int):
    """Obtiene una transacción por su id."""
    for t in _transacciones:
        if t["id"] == transaction_id:
            return t
    raise HTTPException(status_code=404, detail="Transacción no encontrada")
