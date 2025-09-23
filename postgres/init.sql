-- ================================================================
-- SCRIPT COMPLETO DE INICIALIZAÇÃO POSTGRESQL PARA PORTO + GRAFANA
-- ================================================================

-- LOG INICIAL
DO $$
BEGIN
    RAISE NOTICE 'Iniciando configuração do PostgreSQL para Grafana e Dashboard do Porto';
END $$;

-- ================================================================
-- CRIAÇÃO DO USUÁRIO E PERMISSÕES
-- ================================================================
-- Verifica se o usuário já existe antes de criar
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'grafana_admin') THEN
        CREATE ROLE grafana_admin WITH LOGIN PASSWORD 'grafana_password';
        RAISE NOTICE 'Usuário grafana_admin criado';
    ELSE
        RAISE NOTICE 'Usuário grafana_admin já existe';
    END IF;
END
$$;

-- Verifica se o banco já existe
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'grafana_database') THEN
        CREATE DATABASE grafana_database OWNER grafana_admin;
        RAISE NOTICE 'Database grafana_database criado';
    ELSE
        RAISE NOTICE 'Database grafana_database já existe';
    END IF;
EXCEPTION
    WHEN duplicate_database THEN
        RAISE NOTICE 'Database grafana_database já existe';
END
$$;

-- Conecta ao banco grafana_database para executar o resto
\connect grafana_database;

-- Concede permissões
GRANT ALL PRIVILEGES ON DATABASE grafana_database TO grafana_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO grafana_admin;
GRANT CREATE ON SCHEMA public TO grafana_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO grafana_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO grafana_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO grafana_admin;

-- ================================================================
-- CONFIGURAÇÕES ESPECÍFICAS
-- ================================================================
SET timezone = 'UTC';
ALTER USER grafana_admin SET statement_timeout = '60s';
ALTER USER grafana_admin SET lock_timeout = '30s';
ALTER USER grafana_admin SET idle_in_transaction_session_timeout = '300s';

-- ================================================================
-- TABELAS PRINCIPAIS
-- ================================================================

-- ================================================================
-- TABELAS PRINCIPAIS COM CASCADE DELETE
-- ================================================================

-- Cais
CREATE TABLE berths (
    berth_id SERIAL PRIMARY KEY,
    berth_number INTEGER UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'available',
    start_maintenance TIMESTAMP WITH TIME ZONE,
    end_maintenance TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Navios (tabela principal - sem referências)
CREATE TABLE vessels (
    vessel_id SERIAL PRIMARY KEY,
    vessel_name VARCHAR(100) NOT NULL,
    vessel_type VARCHAR(50) NOT NULL,
    priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 3),
    estimated_duration INTEGER NOT NULL DEFAULT 0  -- segundos
);







-- Operações (COM CASCADE DELETE)
CREATE TABLE operations (
    operation_id SERIAL PRIMARY KEY,
    vessel_id INTEGER NOT NULL REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    berth_id INTEGER NOT NULL REFERENCES berths(berth_id),
    operation_type VARCHAR(20) NOT NULL,
    planned_duration INTEGER,  -- segundos (estimativa)
    actual_duration INTEGER,   -- segundos (real)
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'in_progress', 'completed', 'cancelled')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- Fila de navios (COM CASCADE DELETE)
CREATE TABLE vessel_queue (
    vessel_queue_id SERIAL PRIMARY KEY,
    vessel_id INTEGER REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    arrival_time TIMESTAMP NOT NULL,
    start_service_time TIMESTAMP,  -- quando começa a ser atendido
    end_service_time TIMESTAMP,    -- quando termina
    status VARCHAR(20) NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'in_service', 'completed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);



-- Dados alfandegários (COM CASCADE DELETE)
CREATE TABLE customs_clearance (
    clearance_id SERIAL PRIMARY KEY,
    vessel_id INTEGER NOT NULL REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL,
    last_update TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- View de eficiência operacional
CREATE OR REPLACE VIEW v_operational_efficiency AS
SELECT
    NOW() AS timestamp,
    COUNT(*) as total_operations,
    COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as active_operations,
    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_operations,
    CASE
        WHEN COUNT(*) = 0 THEN 0
        ELSE ROUND(100.0 * COUNT(CASE WHEN status = 'in_progress' THEN 1 END) / COUNT(*), 2)
    END AS efficiency_percent
FROM operations;

-- ================================================================
-- VERIFICAÇÃO FINAL
-- ================================================================
DO $$
BEGIN
    RAISE NOTICE 'Verificando criação das tabelas...';
    
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'vessels') THEN
        RAISE NOTICE '✅ Tabela vessels criada com % registros', (SELECT COUNT(*) FROM vessels);
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'operations') THEN
        RAISE NOTICE '✅ Tabela operations criada com % registros', (SELECT COUNT(*) FROM operations);
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'berths') THEN
        RAISE NOTICE '✅ Tabela berths criada com % registros', (SELECT COUNT(*) FROM berths);
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'vessel_queue') THEN
        RAISE NOTICE '✅ Tabela vessel_queue criada com % registros', (SELECT COUNT(*) FROM vessel_queue);
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'customs_clearance') THEN
        RAISE NOTICE '✅ Tabela customs_clearance criada com % registros', (SELECT COUNT(*) FROM customs_clearance);
    END IF;
    
    RAISE NOTICE '🎉 Configuração do banco de dados concluída com sucesso!';
    
    -- Verificar constraints CASCADE
    RAISE NOTICE '🔍 Verificando constraints CASCADE...';
    
    PERFORM 
    FROM information_schema.referential_constraints rc
    JOIN information_schema.table_constraints tc ON rc.constraint_name = tc.constraint_name
    WHERE rc.delete_rule = 'CASCADE' AND tc.table_name IN ('operations', 'vessel_queue', 'customs_clearance');
    
    IF FOUND THEN
        RAISE NOTICE '✅ Constraints CASCADE configuradas corretamente!';
    ELSE
        RAISE NOTICE '⚠️  Constraints CASCADE podem não estar configuradas!';
    END IF;
    
END $$;