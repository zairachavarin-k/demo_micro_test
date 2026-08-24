"""
Pruebas para el Servicio de Transacciones.

La prueba `test_pool_no_se_agota_bajo_carga` es la clave de la demo:
pasa con el código sano y falla con el bug activo, sirviendo como la
'validación automática' que Copilot ejecuta tras proponer el fix.
"""

import concurrent.futures
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_responde():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["estado"] == "online"


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200


def test_listar_transacciones():
    response = client.get("/transactions")
    assert response.status_code == 200
    assert response.json()["count"] > 0


def test_transaccion_no_encontrada():
    response = client.get("/transactions/99999")
    assert response.status_code == 404


def test_pool_no_se_agota_bajo_carga_concurrente():
    """
    Lanza peticiones concurrentes de verdad (no secuenciales), para que
    la fuga de conexiones se manifieste igual que en producción.

    Con el código correcto, todas responden 200.
    Con el bug (pool_leak), el pool se agota y varias fallan con 503.
    """
    def una_peticion(_):
        return client.get("/transactions").status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        codigos = list(executor.map(una_peticion, range(20)))

    assert all(c == 200 for c in codigos), (
        f"Algunas peticiones fallaron: {codigos}. "
        "Posible agotamiento del pool de conexiones."
    )
