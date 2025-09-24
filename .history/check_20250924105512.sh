#!/bin/bash

echo "🔍 === DIAGNÓSTICO COMPLETO === 🔍"
echo ""

# 1. Status dos containers
echo "📦 === STATUS DOS CONTAINERS ==="
docker-compose ps
echo ""

# 2. Health checks
echo "🏥 === HEALTH CHECKS ==="
docker inspect postgres --format='{{json .State.Health}}' | python3 -m json.tool 2>/dev/null || echo "PostgreSQL health check não disponível"
docker inspect grafana --format='{{json .State.Health}}' | python3 -m json.tool 2>/dev/null || echo "Grafana health check não disponível"
echo ""

# 3. Conectividade de rede
echo "🌐 === TESTE DE CONECTIVIDADE ==="
echo "Testando conexão do Grafana para PostgreSQL..."
docker exec grafana sh -c "nc -zv postgres 5432" 2>&1 || echo "❌ Falha na conectividade"
echo ""

# 4. Logs recentes do PostgreSQL
echo "📋 === LOGS RECENTES POSTGRESQL (últimas 6 linhas) ==="
docker logs postgres --tail=5
echo ""

# 5. Logs recentes do Grafana  
echo "📋 === LOGS RECENTES GRAFANA (últimas 20 linhas) ==="
docker logs grafana --tail=
echo ""

# 6. Variáveis de ambiente
echo "⚙️ === VARIÁVEIS DE AMBIENTE ==="
echo "Verificando se as variáveis estão definidas..."
docker exec postgres sh -c 'echo "POSTGRES_DB: $POSTGRES_DB"'
docker exec postgres sh -c 'echo "POSTGRES_USER: $POSTGRES_USER"' 
docker exec postgres sh -c 'echo "POSTGRES_PASSWORD: [DEFINIDA]"'
echo ""

# 7. Teste direto de conexão PostgreSQL
echo "🔌 === TESTE DIRETO POSTGRESQL ==="
echo "Testando conexão direta ao PostgreSQL..."
docker exec postgres sh -c 'pg_isready -U $POSTGRES_USER -d $POSTGRES_DB' || echo "❌ PostgreSQL não está pronto"
echo ""

# 8. Verificar se há dados nas tabelas
echo "📊 === VERIFICAR DADOS NAS TABELAS ==="
echo "Listando tabelas no banco..."
docker exec postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"' 2>/dev/null || echo "❌ Não foi possível listar tabelas"
echo ""

# 9. Testar query simples
echo "🔍 === TESTE DE QUERY SIMPLES ==="
echo "Executando SELECT 1..."
docker exec postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1 as test;"' 2>/dev/null || echo "❌ Não foi possível executar query"
echo ""

# 10. Verificar configuração do Grafana
echo "⚙️ === CONFIGURAÇÃO GRAFANA ==="
echo "Verificando se o datasource está configurado..."
docker exec grafana sh -c "ls -la /etc/grafana/provisioning/datasources/" 2>/dev/null || echo "❌ Diretório de datasources não encontrado"
echo ""

echo "🎯 === RESUMO DO DIAGNÓSTICO ==="
echo "✅ Containers rodando: $(docker-compose ps | grep -c 'Up')"
echo "✅ PostgreSQL healthy: $(docker inspect postgres --format='{{.State.Health.Status}}' 2>/dev/null || echo 'unknown')"
echo "✅ Grafana healthy: $(docker inspect grafana --format='{{.State.Health.Status}}' 2>/dev/null || echo 'unknown')"
echo ""
echo "📝 Próximos passos sugeridos:"
echo "1. Se algum container não está healthy, reinicie: docker-compose restart [service]"
echo "2. Se há erros de conectividade, verifique a rede: docker network ls"
echo "3. Se PostgreSQL não tem dados, verifique o script init.sql"
echo "4. Teste o datasource manualmente no Grafana UI"