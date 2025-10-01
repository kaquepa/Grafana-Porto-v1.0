#!/bin/bash

set -e

echo "🚀 VINCULANDO PAINÉIS AO DATASOURCE EXISTENTE"
echo "=============================================="

# Configurações
GRAFANA_URL="http://localhost:3000"
API_KEY_FILE="./grafana/grafana_api_key.txt"
DATASOURCE_UID="postgres-porto-uid"
DASHBOARD_UID="Porto"

echo "📁 Procurando API Key em: $(pwd)/$API_KEY_FILE"

# Verifica se API Key existe
if [ ! -f "$API_KEY_FILE" ]; then
    echo "❌ ERRO: Arquivo API Key não encontrado: $API_KEY_FILE"
    exit 1
fi

echo "✅ API Key encontrado: $API_KEY_FILE"

# Aguarda Grafana ficar pronto
echo "⏳ Aguardando Grafana em: $GRAFANA_URL"
max_attempts=10
attempt=1
while [ $attempt -le $max_attempts ]; do
    if curl -s "$GRAFANA_URL/api/health" > /dev/null; then
        echo "✅ Grafana está pronto!"
        break
    fi
    echo "   Tentativa $attempt/$max_attempts..."
    sleep 2
    ((attempt++))
    
    if [ $attempt -gt $max_attempts ]; then
        echo "❌ ERRO: Grafana não responde em $GRAFANA_URL"
        exit 1
    fi
done

# Obtém API Key
API_KEY=$(cat "$API_KEY_FILE")
echo "✅ API Key carregado"

# 1. Verifica se o datasource existe (MÉTODO COMPATÍVEL macOS)
echo "🔍 Verificando datasource..."
DS_RESPONSE=$(curl -s \
    -H "Authorization: Bearer $API_KEY" \
    -w "HTTP_CODE:%{http_code}" \
    "$GRAFANA_URL/api/datasources/uid/$DATASOURCE_UID")

# Extrai HTTP_CODE de forma compatível com macOS
HTTP_CODE=$(echo "$DS_RESPONSE" | grep -o 'HTTP_CODE:[0-9]*' | cut -d: -f2)
DS_CONTENT=$(echo "$DS_RESPONSE" | sed 's/HTTP_CODE:[0-9]*//')

if [ "$HTTP_CODE" != "200" ]; then
    echo "❌ ERRO: Datasource não encontrado (HTTP $HTTP_CODE)"
    exit 1
fi

echo "✅ Datasource encontrado: $DATASOURCE_UID"

# 2. Verifica se o dashboard existe
echo "🔍 Verificando dashboard..."
DASH_RESPONSE=$(curl -s \
    -H "Authorization: Bearer $API_KEY" \
    -w "HTTP_CODE:%{http_code}" \
    "$GRAFANA_URL/api/dashboards/uid/$DASHBOARD_UID")

HTTP_CODE=$(echo "$DASH_RESPONSE" | grep -o 'HTTP_CODE:[0-9]*' | cut -d: -f2)
DASH_CONTENT=$(echo "$DASH_RESPONSE" | sed 's/HTTP_CODE:[0-9]*//')

if [ "$HTTP_CODE" != "200" ]; then
    echo "❌ ERRO: Dashboard não encontrado (HTTP $HTTP_CODE)"
    exit 1
fi

echo "✅ Dashboard encontrado: $DASHBOARD_UID"

# 3. Extrai e modifica os painéis
echo "🔧 Modificando painéis para usar datasource..."
MODIFIED_DASHBOARD=$(echo "$DASH_CONTENT" | python3 -c "
import json, sys

try:
    data = json.load(sys.stdin)
    dashboard = data['dashboard']
    panels = dashboard.get('panels', [])
    
    print(f'📋 Encontrados {len(panels)} painéis', file=sys.stderr)
    
    # Modifica cada painel
    panels_modified = 0
    for i, panel in enumerate(panels):
        panel_title = panel.get('title', f'Painel {i+1}')
        
        # Força datasource no painel
        panel['datasource'] = {
            'type': 'postgres',
            'uid': '$DATASOURCE_UID'
        }
        
        # Força datasource em cada target
        targets_modified = 0
        for target in panel.get('targets', []):
            target['datasource'] = {
                'type': 'postgres', 
                'uid': '$DATASOURCE_UID'
            }
            targets_modified += 1
        
        print(f'   ✅ {panel_title}: {targets_modified} targets modificados', file=sys.stderr)
        panels_modified += 1
    
    print(f'🎯 Total: {panels_modified} painéis modificados', file=sys.stderr)
    
    # Prepara payload de atualização
    result = {
        'dashboard': dashboard,
        'overwrite': True,
        'message': 'Painéis vinculados automaticamente ao datasource'
    }
    
    print(json.dumps(result))
    
except Exception as e:
    print(f'❌ ERRO no Python: {e}', file=sys.stderr)
    sys.exit(1)
")

if [ $? -ne 0 ]; then
    echo "❌ ERRO: Falha ao modificar painéis"
    exit 1
fi

# 4. Atualiza o dashboard
echo "💾 Atualizando dashboard..."
UPDATE_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    -d "$MODIFIED_DASHBOARD" \
    -w "HTTP_CODE:%{http_code}" \
    "$GRAFANA_URL/api/dashboards/db")

HTTP_CODE=$(echo "$UPDATE_RESPONSE" | grep -o 'HTTP_CODE:[0-9]*' | cut -d: -f2)
UPDATE_CONTENT=$(echo "$UPDATE_RESPONSE" | sed 's/HTTP_CODE:[0-9]*//')

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ DASHBOARD ATUALIZADO COM SUCESSO!"
    # Extrai URL do dashboard
    DASH_URL=$(echo "$UPDATE_CONTENT" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('url', 'N/A'))" 2>/dev/null || echo "N/A")
    echo "🔗 URL: $GRAFANA_URL$DASH_URL"
else
    echo "❌ ERRO na atualização (HTTP $HTTP_CODE)"
    echo "   Response: $UPDATE_CONTENT"
    exit 1
fi

echo ""
echo "==========================================="
echo "🎯 CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!"
echo "✅ Datasource verificado: $DATASOURCE_UID"
echo "✅ Dashboard atualizado: $DASHBOARD_UID" 
echo "✅ Painéis vinculados ao datasource"
echo "✅ Dados devem aparecer AUTOMATICAMENTE"
echo "==========================================="