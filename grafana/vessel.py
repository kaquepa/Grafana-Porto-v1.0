# ================================================================
# GERADOR DE DADOS FAKE  
# ================================================================

import random, tabulate, pandas
from datetime import datetime, timedelta
from typing import List, Dict, Any
from enum import Enum
from datetime import timezone


# Faker sem múltiplos locales para evitar o erro
from faker import Faker
import sys, os 

# Configurar Faker com um único locale
fake = Faker('pt_PT')   

# ================================================================
# ENUMS LOCAIS ( 
# ================================================================

class ShipType(Enum):
    CONTAINER = "Container"
    TANKER = "Tanker"
    GERAL = "Carga Geral"

# ================================================================
# DADOS MARÍTIMOS  
# ================================================================

# Nomes de navios realistas por tipo
SHIP_NAMES = {
    'Container': [
        'EVER GIVEN', 'MAERSK MADRID', 'CMA CGM MARCO POLO', 'MSC GÜLSÜN',
        'HAPAG MONTREAL', 'COSCO SHIPPING', 'ONE INNOVATION', 'YANG MING WISDOM',
        'EVERGREEN ETERNAL', 'HAMBURG EXPRESS', 'MADRID BRIDGE', 'LISBON STAR',
        'PORTO MARAVILHA', 'ATLANTIC PIONEER', 'EUROPA CONTAINER', 'OCEAN ALLIANCE'
    ],
    'Tanker': [
        'PETRO STAR', 'CRUDE OCEAN', 'OIL MAJESTY', 'ENERGY PIONEER',
        'ATLANTIC CRUDE', 'BRENT NAVIGATOR', 'EUROPA PETROLEUM', 'FUEL MASTER',
        'LIQUID GOLD', 'OCEANIC FUEL', 'TANKER SUPREME', 'PORTO PETRÓLEO',
        'GALP ENERGIA', 'REPSOL SPIRIT', 'BP EXPLORER', 'SHELL NAVIGATOR'
    ],
    'Carga Geral': [
        'GENERAL CARGO', 'BULK MASTER', 'CARGO EXPRESS', 'FREIGHT STAR',
        'UNIVERSAL TRADER', 'MULTI PURPOSE', 'GLOBAL CARRIER', 'CARGO PIONEER',
        'TRADING VESSEL', 'COMMERCIAL STAR', 'PORTO COMERCIAL', 'AVEIRO TRADER',
        'IBERIAN CARGO', 'ATLANTIC TRADER', 'EUROPA FREIGHT', 'MEDITERRANEAN CARGO'
    ]
}

# Tempos de serviço realistas por tipo (em horas)
SERVICE_HOURS = {
    'Container': (8, 16),    # Containers são mais rápidos
    'Tanker': (6, 12),       # Tanques líquidos, bombeamento
    'Carga Geral': (12, 24)  # Carga geral demora mais
}

# Companhias marítimas
SHIPPING_COMPANIES = [
    'Maersk Line', 'CMA CGM', 'COSCO Shipping', 'Hapag-Lloyd',
    'ONE (Ocean Network Express)', 'Evergreen Marine', 'Yang Ming',
    'MSC Mediterranean Shipping', 'Hamburg Süd', 'ZIM Integrated Shipping'
]

# ================================================================
# GERADOR GLOBAL 
# ================================================================

class VesselGenerator:
    """Gerador simplificado sem dependências complexas"""
    
    def __init__(self):
        self.ship_counter = 1
    
    def generate_ship_id(self) -> str:
        """Gera ID correto: N001, N002, N003..."""
        ship_id = f"N{self.ship_counter:03d}"
        self.ship_counter += 1
        return ship_id
    
    def get_random_ship_name(self, ship_type: str) -> str:
        """Seleciona o nome baseado no tipo"""
        names = SHIP_NAMES.get(ship_type, SHIP_NAMES['Carga Geral'])
        return random.choice(names)
    
    def _get_realistic_service_hours(self, ship_type: str) -> str:
        """Gera datetime de serviço realista e retorna como string formatada"""
        min_hours, max_hours = SERVICE_HOURS.get(ship_type, (8, 16))
        now = datetime.now()
        hours_to_add = random.randint(min_hours, max_hours)
        minutes_to_add = random.randint(0, 59)
        seconds_to_add = random.randint(0, 59)
        dt = now + timedelta(hours=hours_to_add, minutes=minutes_to_add, seconds=seconds_to_add)
        return timedelta(hours=hours_to_add, minutes=minutes_to_add, seconds=seconds_to_add)
    def get_realistic_service_hours(self, ship_type: str) -> timedelta:
        min_h, max_h = SERVICE_HOURS.get(ship_type, (8, 16))
        hours = random.randint(min_h, max_h)
        minutes = random.randint(0, 59)
        return random.randint(min_h, max_h) # timedelta(hours=hours, minutes=minutes)
    
    def generate_fake_ship_data(self) -> Dict[str, Any]:
        ship_type = random.choice([ship.value for ship in ShipType])  # strings
        arrival_time = fake.date_time_between(
                                                    start_date='-7d',
                                                    end_date='now'#,
                                                    #tzinfo=timezone.utc
                                                    )
        arrival_time_clean = arrival_time.replace(microsecond=0)
        
        return {
            "vessel_name": self.get_random_ship_name(ship_type),
            "vessel_type": random.choices(["import", "export"], weights = [0.7, 0.3])[0],
            "priority": random.randint(1, 3),
            "estimated_duration": self.get_realistic_service_hours(ship_type),  # timedelta ✅
        }
 
# Criar uma única instância para manter o contador persistente
_global_generator = VesselGenerator()

# ================================================================
# FUNÇÕES PRINCIPAIS  
# ================================================================

def generate__vessel_data():
    """Função compatível com seu código original"""
    global _global_generator
    return _global_generator.generate_fake_ship_data()



ships_gerados = generate__vessel_data()
ships_gerados = pandas.DataFrame ([ships_gerados])
print(ships_gerados.to_markdown())

 
 
 
 
