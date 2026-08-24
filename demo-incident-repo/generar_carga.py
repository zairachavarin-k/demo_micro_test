"""
Generador de carga para provocar el incidente en vivo.

Uso:
    python generar_carga.py --url http://localhost:8000
    python generar_carga.py --url https://tu-app.azurecontainerapps.io
"""

import argparse
import concurrent.futures
import statistics
import time
import httpx


def una_peticion(url):
    inicio = time.time()
    try:
        r = httpx.get(f"{url}/transactions", timeout=15.0)
        return (r.status_code == 200, (time.time() - inicio) * 1000)
    except Exception:
        return (False, (time.time() - inicio) * 1000)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--peticiones", type=int, default=50)
    parser.add_argument("--concurrencia", type=int, default=15)
    args = parser.parse_args()

    print(f"Lanzando {args.peticiones} peticiones "
          f"({args.concurrencia} concurrentes) a {args.url}\n")

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concurrencia
    ) as executor:
        resultados = list(executor.map(
            lambda _: una_peticion(args.url), range(args.peticiones)
        ))

    exitos = sum(1 for ok, _ in resultados if ok)
    fallos = args.peticiones - exitos
    latencias = [lat for _, lat in resultados]

    print(f"Exitosas: {exitos}/{args.peticiones}")
    print(f"Fallidas: {fallos}/{args.peticiones}")
    print(f"Latencia media: {round(statistics.mean(latencias), 1)} ms")

    if fallos > 0:
        print("\n⚠️  INCIDENTE: el servicio está degradado.")
    else:
        print("\n✅  Servicio sano.")


if __name__ == "__main__":
    main()
