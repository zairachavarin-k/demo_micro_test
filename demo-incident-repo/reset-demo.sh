#!/bin/bash
# ============================================================
# RESET DE LA DEMO
# ============================================================
# Ejecuta este script después de cada corrida de la demo para
# devolver el sistema al estado inicial (con el bug activo,
# listo para repetir la demo).
#
# Uso: bash reset-demo.sh
# ============================================================

set -e  # detener ante cualquier error

echo "🔄 Iniciando reset de la demo..."
echo ""

# Paso 1: Traer cualquier cambio del remoto (por si Copilot mergeó el fix)
echo "📥 Sincronizando con GitHub..."
git pull --no-edit

# Paso 2: Buscar el commit del fix más reciente y revertirlo
echo "🔍 Buscando commits de fix aplicados..."
FIX_COMMIT=$(git log --oneline --grep="fix\|Fix\|release connection" -n 1 --format="%H")

if [ -n "$FIX_COMMIT" ]; then
    # Verificar si NO es ya un revert (evitar revertir el revert)
    IS_REVERT=$(git log --oneline -n 1 --format="%s" $FIX_COMMIT | grep -c "Revert" || true)

    if [ "$IS_REVERT" = "0" ]; then
        # Verificar si este fix ya fue revertido después
        ALREADY_REVERTED=$(git log --oneline | grep -c "Revert.*$(git log -1 --format='%s' $FIX_COMMIT | cut -c1-40)" || true)

        if [ "$ALREADY_REVERTED" = "0" ]; then
            echo "↩️  Revirtiendo el fix aplicado: $FIX_COMMIT"
            git revert $FIX_COMMIT --no-edit
            echo "📤 Subiendo el revert a GitHub..."
            git push
        else
            echo "✅ El fix ya fue revertido previamente, nada que hacer en git."
        fi
    fi
else
    echo "✅ No se encontraron commits de fix pendientes de revertir."
fi

# Paso 3: Confirmar que Azure tiene FAULT_MODE=pool_leak
echo ""
echo "☁️  Verificando estado de Azure Container App..."
az containerapp update \
  --name demo-incident-fastapi \
  --resource-group Mexico-Laboratorios \
  --container-name demo-incident-fastapi \
  --set-env-vars FAULT_MODE=pool_leak \
  --output none

echo "⏳ Esperando 30 segundos a que la nueva revisión active..."
sleep 30

# Paso 4: Confirmar que la app responde con el bug activo
echo ""
echo "🧪 Verificando que el bug está activo..."
RESPUESTA=$(curl -s https://demo-incident-fastapi.happytree-b4cd96ac.eastus.azurecontainerapps.io/)
echo "Respuesta: $RESPUESTA"

if echo "$RESPUESTA" | grep -q "pool_leak"; then
    echo ""
    echo "✅ RESET COMPLETO. La demo está lista para correrse de nuevo."
    echo ""
    echo "📋 Recordatorios antes de empezar:"
    echo "   1. Cierra el Issue anterior del SRE Agent en GitHub (opcional)."
    echo "   2. Cierra cualquier Pull Request abierto de Copilot."
    echo "   3. Abre una sesión NUEVA en github.com/copilot para el canvas."
else
    echo ""
    echo "⚠️  Algo no salió bien. La app no responde con pool_leak."
    echo "    Revisa manualmente el estado en el portal de Azure."
fi
