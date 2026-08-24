# Imagen ligera para desplegar en Azure Container Apps.
FROM python:3.12-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# FAULT_MODE se controla en Azure como variable de entorno del contenedor,
# así se puede prender/apagar el incidente sin reconstruir la imagen.
ENV FAULT_MODE=none

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
