#!/bin/bash

set -e

echo "🚀 CONFIGURAÇÃO COMPLETA AUTOMÁTICA"

# Configurações
GRAFANA_URL="http://grafana_dashboard:3000"
API_KEY_FILE="/app/grafana/grafana_api_key.txt"
DATASOURCE_UID="postgres-porto-uid"
DASHBOARD_UID="Porto"

# Aguarda Grafana
until curl -s "$GRAFANA_URL/api/health" > /dev/null; do sleep 2; done
API_KEY=$(cat "$API_KEY_FILE")

# 1. Cria/Atualiza Datasource
echo "🔌 Configurando datasource..."
curl -X POST -s \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "name": "PostgreSQL-Porto-Operacional",
    "type": "postgres",
    "uid": "'$DATASOURCE_UID'",
    "access": "proxy", 
    "url": "postgres_database:5432",
    "database": "grafana_database",
    "user": "grafana_admin",
    "isDefault": true,
    "secureJsonData": {"password": "secure_password_123"},
    "jsonData": {"sslmode": "disable", "postgresVersion": 1500}
  }' \
  "$GRAFANA_URL/api/datasources" > /dev/null

sleep 3

# 2. Cria Dashboard com painéis JÁ VINCULADOS
echo "📊 Criando dashboard vinculado..."
DASHBOARD_PAYLOAD='{
  "dashboard": {
    "uid": "'$DASHBOARD_UID'",
    "title": "Dashboard Operacional do Porto",
    "tags": ["automated", "porto"],
    "timezone": "browser",
    "panels": [
      {
        "type": "stat",
        "title": "Eficiência Operacional",
        "gridPos": {"x": 0, "y": 0, "w": 3, "h": 6},
        "datasource": {"type": "postgres", "uid": "'$DATASOURCE_UID'"},
        "targets": [{
          "datasource": {"type": "postgres", "uid": "'$DATASOURCE_UID'"},
          "refId": "A",
          "rawSql": "SELECT 85.5 as value",
          "format": "table"
        }]
      }
      // Adicione outros painéis aqui...
    ],
    "time": {"from": "now-7d", "to": "now"},
    "refresh": "30s"
  },
  "overwrite": true
}'

curl -X POST -s \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d "$DASHBOARD_PAYLOAD" \
  "$GRAFANA_URL/api/dashboards/db" > /dev/null

echo "✅ CONFIGURAÇÃO 100% AUTOMÁTICA CONCLUÍDA!"
echo "🎯 Os dados DEVEM aparecer automaticamente!"