# 🚢 Simulador Portuario  – Dashboard & FastAPI

![Docker](https://img.shields.io/badge/Docker-✓-blue?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-✓-green?style=flat-square)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-✓-blue?style=flat-square)
![Grafana](https://img.shields.io/badge/Grafana-✓-orange?style=flat-square)

Sistema completo de **monitoramento e simulação portuária** em tempo real, integrando visualizações animadas com dashboards profissionais.

## ✨ Características Principais

- **🌊 Simulação Realista**: Animação de navios, gruas e movimentação de contêineres
- **📊 Dashboard em Tempo Real**: Métricas operacionais via Grafana
- **🐘 Base de Dados Robustos**: PostgreSQL para armazenamento de dados
- **⚡ API Moderna**: FastAPI com endpoints RESTful
- **🐳 Containerização Completa**: Docker Compose para orquestração
- **🔧 Automação Total**: Configuração automática de tokens e dashboards

## 🏗️ Arquitetura do Sistema

```text
porto-operacional/
├── docker-compose.yml          # Orquestração de serviços
├── .env.example               # Variáveis de ambiente modelo
├── README.md
│
├── frontend/                   # Aplicação FastAPI
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                # Aplicação principal
│   ├── core/
│   │   └── config.py          # Configurações
│   ├── routes/
│   │   └── pipeline.py        # Endpoints da API
│   ├── static/
│   │   ├── script.js          # Animação do porto
│   │   └── style.css          # Estilos responsivos
│   └── templates/
│       └── index.html         # Página principal
│
├── grafana/                   # Configuração do Grafana
│   ├── provisioning/
│   │   ├── dashboards/
│   │   │   └── dashboard.yml  # Dashboard automático
│   │   ├── datasources/
│   │   │   └── datasource.yml # Conexão PostgreSQL
│   │   └── notifiers/
│   │       └── notifiers.yml  # Configurações de alerta
│   ├── create_dashboard.py    # Criação automática de dashboard
│   ├── create_service_account.py # Autenticação
│   └── streaming.py           # Simulador de dados
│
└── postgres/                  # Configuração do banco
    └── init.sql              # Schema inicial
```
---
# 🚀 Quick Start

Pré-requisitos

- Docker ≥ 20.10
- Docker Compose ≥ 2.0
- 4GB RAM disponível

Instalação em 3 Passos

```bash
# 1. Clone o repositório
git clone https://github.com/kaquepa/Grafana-Porto-v1.0.git
cd Grafana-Porto-v1.0

# 2. Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env conforme necessário
```

```bash
# 3. Inicie os serviços
docker compose up -d --build
```
⚡ Serviços Disponíveis
| Serviço       | URL                       | Porta | Descrição                       |
|:------------: |---------------------------|:----: |----------------------------------|
| 🖥️ **Frontend**   | [http://localhost:8000](http://localhost:8000) | 8000 | Interface web com animações do porto |
| 📊 **Grafana**    | [http://localhost:3000](http://localhost:3000) | 3000 | Dashboards em tempo real *(login padrão: admin/admin)* |
| 🗄️ **Adminer**    | [http://localhost:8080](http://localhost:8080) | 8080 | Interface web para o banco de dados |
| 🐘 **PostgreSQL** | `localhost:5432`                           | 5432 | Banco de dados relacional |


## 🎮 Como Usar

1. Visualização do Porto
```bash 
Acesse http://localhost:8000 para ver a simulação em ação:

. Navios dinâmicos chegando e saindo
. Gruas movimentando contêineres automaticamente
```
```test
Interface responsiva para desktop e mobile
```
2. Monitoramento via Grafana
```bash 
Acesse http://localhost:3000 (admin/admin) para:

. Dashboard operacional em tempo real
. Métricas de eficiência portuária
. Indicadores de ocupação e produtividade
```

## 3. Gestão de Dados
```bash 
Acesse http://localhost:8080 para:
. Verificar estados dos cais diretamente no banco
. Executar consultas SQL
. Monitorar a integridade dos dados
```

---
## 🔌 API Endpoints
- Estado dos Cais
```bash
http
GET /api/v1/estado-cais
```
Resposta:
```bash
json
[
  {
    "berth_id": 1,
    "ocupado": true,
    "status": "occupied"
  },
  {
    "berth_id": 2,
    "ocupado": true,
    "status": "occupied"
  },
  {
    "berth_id": 3,
    "ocupado": true,
    "status": "occupied"
  },
  {
    "berth_id": 4,
    "ocupado": false,
    "status": "occupied"
  }
]
````

## ⚙️ Configuração

Variáveis de Ambiente (.env)
```bash
env
# PostgreSQL
- POSTGRES_DB=porto
- POSTGRES_USER=porto_user
- POSTGRES_PASSWORD=sua_senha_segura
- POSTGRES_HOST=postgres
- POSTGRES_PORT=5432

# Grafana
- GF_SECURITY_ADMIN_USER=admin
- GF_SECURITY_ADMIN_PASSWORD=admin
- GF_SECURITY_ALLOW_EMBEDDING=true
- GRAFANA_URL=http://localhost:3000

# Frontend
FRONTEND_PORT=8000
DEBUG=false
```
Personalização da Animação
```javascript
Edite frontend/static/script.js para ajustar:


javascript
// Velocidades da animação
const velocidadeVertical = 0.6;
const velocidadeHorizontal = 0.3;
const tempoPausa = 2000;

// Número de gruas por tamanho de tela
const totalNavios = screenWidth <= 480 ? 1 : 
                   screenWidth <= 768 ? 2 : 
                   screenWidth <= 1024 ? 3 : 4;
```
---
## 🐳 Comandos Docker Úteis
```bash 
bash
# Ver status dos serviços
docker compose ps

# Ver logs em tempo real
docker compose logs -f frontend

# Reiniciar um serviço específico
docker compose restart grafana

# Parar todos os serviços
docker compose down

# Parar e remover volumes (dados)
docker compose down -v

# Rebuildar uma imagem
docker compose build frontend
```
---
## 🔧 Troubleshooting

Problemas Comuns
- Portas ocupadas:
```bash
bash
# Verifique quais processos estão usando as portas
sudo lsof -i :8000
sudo lsof -i :3000
Erro de permissão:

bash
# Dê permissão aos scripts
chmod +x grafana/*.py
Problemas no banco:

bash
# Teste a conexão com o PostgreSQL
docker compose exec postgres psql -U porto_user -d porto -c "SELECT * FROM berths;"
Logs e Debug

bash
# Logs completos do sistema
docker compose logs

# Logs específicos com timestamps
docker compose logs -f --tail=50 frontend

# Verificar saúde dos containers
docker compose ps
````

## 🤝 Contribuindo
```bash
Fork o projeto
. Crie uma branch para sua feature (git checkout -b feature/AmazingFeature)
. Commit suas mudanças (git commit -m 'Add some AmazingFeature')
. Push para a branch (git push origin feature/AmazingFeature)
. Abra um Pull Request
```
---
## 📄 Licença

Distribuído sob licença MIT. Veja LICENSE para mais informações.

## 👥 Autor

Domingos Graciano - Desenvolvimento Inicial - github.com/kaquepa