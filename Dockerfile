# Lightweight reviewer image for AerialClaw mock-mode evaluation.
# It intentionally does not include PX4/Gazebo/AirSim.
FROM python:3.12-slim AS backend
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SIM_ADAPTER=mock \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=5001
COPY requirements-mock.txt ./
RUN pip install --no-cache-dir -r requirements-mock.txt
COPY . .

FROM node:22-slim AS frontend
WORKDIR /ui
COPY ui/package*.json ./
RUN npm install
COPY ui/ ./
RUN npm run build

FROM backend AS final
COPY --from=frontend /ui/dist /app/ui/dist
EXPOSE 5001
CMD ["python", "server.py"]
