# Servicio de Transacciones — Demo de Incidente (SRE Agent + Copilot)

API en **FastAPI** con un pool de conexiones simulado en memoria (sin
necesidad de PostgreSQL ni Docker externo). Reproduce, de forma
controlada, un **agotamiento del pool de conexiones** bajo carga
concurrente — pensado para desplegarse en Azure y ser investigado por
el **Azure SRE Agent**, con la corrección hecha por **GitHub Copilot**.

---

## 🖥️ Parte 1: Probarlo en local (2 minutos)

```bash
pip install -r requirements.txt

# Arrancar en modo sano
export FAULT_MODE=none
uvicorn app.main:app --reload
```
Abre http://localhost:8000 — verás el servicio online.

Correr las pruebas:
```bash
pytest -v
```

Provocar el incidente (en otra terminal, con el server corriendo):
```bash
export FAULT_MODE=pool_leak
# reinicia uvicorn con esta variable, luego:
python generar_carga.py --url http://localhost:8000
```
Verás la tasa de error dispararse. Con `FAULT_MODE=none`, todo pasa.

---

## ☁️ Parte 2: Desplegar en Azure (para que el SRE Agent lo investigue)

El SRE Agent necesita un recurso real de Azure para monitorear.
La forma más simple es **Azure Container Apps**.

### Opción rápida: Azure Portal
1. En [portal.azure.com](https://portal.azure.com), crea un
   **Container App** nuevo.
2. En "Container image", elige "Build from GitHub" y apunta a este
   repositorio (usa el `Dockerfile` incluido).
3. En variables de entorno, agrega `FAULT_MODE=none` (para empezar sano).
4. Despliega. Anota la URL pública que te da Azure.

### Opción CLI (si prefieres terminal)
```bash
az containerapp up \
  --name demo-transacciones \
  --resource-group <tu-resource-group> \
  --location eastus2 \
  --source . \
  --env-vars FAULT_MODE=none \
  --target-port 8000 \
  --ingress external
```

### Provocar el incidente en Azure
Cambia la variable de entorno `FAULT_MODE` a `pool_leak` desde el
portal (Container App → Containers → Environment variables) y reinicia
la revisión. Luego, desde tu compu:
```bash
python generar_carga.py --url https://<tu-url>.azurecontainerapps.io
```

---

## 🔍 Parte 3: Conectar el Azure SRE Agent

1. En sre.azure.com, en tu agente, ve a **Azure resources** y agrega el
   resource group donde desplegaste este Container App.
2. En **Code**, conecta este repositorio de GitHub — así el agente
   puede correlacionar el incidente con el código.
3. Con el incidente activo (`FAULT_MODE=pool_leak` + carga generada),
   pídele al agente: *"Investiga por qué el servicio de transacciones
   tiene errores y alta latencia."*

---

## 🤖 Parte 4: GitHub Copilot arregla el bug

En VS Code, con Copilot en **modo Agent**:

> Investiga este repositorio. El servicio se degrada bajo carga
> concurrente con errores 503 y latencia alta. Encuentra la causa raíz
> en `app/db_pool.py`, sin aplicar cambios todavía.

Copilot debería señalar que en modo `pool_leak`, la conexión no se
libera en `ejecutar_consulta_simulada()`. Luego:

> Aplica la corrección para que la conexión siempre se libere, y corre
> las pruebas con pytest para validar.

---

## 🎨 Parte 5: Canvas (opcional)

En la GitHub Copilot app, dentro de una sesión de agente sobre este
repo, usa:
```
/create-canvas Muéstrame el estado del incidente: latencia, tasa de
error, y el plan de investigación y remediación como un tablero visual.
```

---

## Estructura del proyecto

```
demo-incident-repo/
├── app/
│   ├── main.py       # API FastAPI (endpoints)
│   └── db_pool.py     # Pool simulado + el bug conmutable
├── tests/
│   └── test_transactions.py
├── generar_carga.py   # Genera carga para provocar el incidente
├── Dockerfile          # Para desplegar en Azure Container Apps
├── requirements.txt
└── README.md
```

## Dónde está el bug

`app/db_pool.py`, función `ejecutar_consulta_simulada()`. En modo
`pool_leak`, el bloque `finally` omite a propósito liberar la conexión.
La corrección correcta: liberar siempre la conexión, sin importar el modo.
