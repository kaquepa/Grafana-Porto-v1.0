


from datetime import datetime, time, timedelta
import psycopg2, tabulate
import logging, random, os, pandas 
from colorama import init, Fore, Style
from vessel import generate__vessel_data

import time
from datetime import datetime, timedelta
import logging, psycopg2
from colorama import init, Fore, Style
from tabulate import tabulate

init(autoreset=True)
logger = logging.getLogger(__name__)

class PortDataSimulator:
    def __init__(self, berths_count=4, tick_seconds=1, new_ship_interval=5):
        self.berths_count = berths_count
        self.berths = [None] * berths_count
        self.waiting_queue = []
        self.tick_seconds = tick_seconds
        self.new_ship_interval = new_ship_interval
        self.last_ship_time = datetime.now()
        self.ship_counter = 0

        # Estatísticas para simulação
        self.total_ships_handled = 0
        self.total_wait_time = 0
        self.total_service_time = 0
        self.berth_occupancy_time = [0] * berths_count
        self.start_time = datetime.now()
        self.history = []
        self.events = []

        # Possibilidade de manutenção dos cais
        self.berth_maintenance = [None] * berths_count
        
        # Conexão com o banco de dados
        self.db_connection = self.connect_to_database()
        self.initialize_database()

    def connect_to_database(self):
        """Estabelece conexão com o banco de dados PostgreSQL"""
        try:
            conn = psycopg2.connect(
                dbname="grafana_database",
                user="grafana_admin", 
                password="secure_password_123",
                host="postgres",
                port="5432"
            )
            logger.info("✅ Conectado ao banco de dados PostgreSQL")
            return conn
        except Exception as e:
            logger.error(f"❌ Erro ao conectar ao banco de dados: {e}")
            return None

    def initialize_database(self):
        """Inicializa o banco com dados básicos dos cais"""
        if not self.db_connection:
            return
            
        try:
            cursor = self.db_connection.cursor()
            
            # Verificar e inicializar cais se necessário
            cursor.execute("SELECT COUNT(*) FROM berths")
            berth_count = cursor.fetchone()[0]
            
            if berth_count == 0:
                logger.info("🔧 Inicializando cais na base de dados...")
                for i in range(1, self.berths_count + 1):
                    cursor.execute(
                        "INSERT INTO berths (berth_number, status) VALUES (%s, %s)",
                        (i, 'available')
                    )
                
                self.db_connection.commit()
                logger.info("✅ Cais inicializados")
            
            cursor.close()
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar banco: {e}")
            if self.db_connection:
                self.db_connection.rollback()

    def generate_ship_data(self):
        """Gera dados realistas de um navio"""
        self.ship_counter += 1
        
        # Tipos de navios com características realistas
        ship_types = [
            ("Cargueiro", 1, (300, 600), "import"),
            ("Porta-Container", 2, (400, 800), "import"), 
            ("Tanker", 3, (500, 900), "import"),
            ("Bulk Carrier", 1, (350, 700), "export"),
            ("RoRo", 2, (200, 400), "export"),
            ("Frigorífico", 3, (450, 750), "import")
        ]
        
        ship_type, priority, duration_range, operation = random.choice(ship_types)
        service_duration = random.randint(duration_range[0], duration_range[1])
        
        # Gera nome realista do navio
        prefixes = ["MV", "MS", "MT", "SS"]
        names = ["Atlantic", "Pacific", "Mediterranean", "Baltic", "Nordic", "Iberian", 
                "Phoenix", "Titan", "Neptune", "Poseidon", "Explorer", "Navigator"]
        
        ship_name = f"{random.choice(prefixes)} {random.choice(names)} {self.ship_counter}"
        
        # Status alfandegário realista
        customs_statuses = ["pending", "under_review", "approved"]
        customs_weights = [0.3, 0.2, 0.5]  # 50% aprovado, 30% pendente, 20% em revisão
        customs_status = random.choices(customs_statuses, weights=customs_weights)[0]
        
        return {
            'name': ship_name,
            'type': ship_type,
            'priority': priority,
            'service_duration': service_duration,
            'operation_type': operation,
            'customs_status': customs_status,
            'arrival_time': datetime.now()
        }

    def insert_vessel_to_db(self, ship_data):
        """Insere dados do navio na base de dados"""
        if not self.db_connection:
            return None
            
        try:
            cursor = self.db_connection.cursor()
            
            # Inserir navio na tabela vessels
            cursor.execute(
                """INSERT INTO vessels 
                   (vessel_name, vessel_type, priority, estimated_duration) 
                   VALUES (%s, %s, %s, %s) 
                   RETURNING vessel_id""",
                (ship_data['name'], ship_data['type'], 
                 ship_data['priority'], ship_data['service_duration'])
            )
            vessel_id = cursor.fetchone()[0]
            
            # Inserir dados alfandegários
            cursor.execute(
                """INSERT INTO customs_clearance 
                   (vessel_id, status) 
                   VALUES (%s, %s)""",
                (vessel_id, ship_data['customs_status'])
            )
            
            # Inserir na fila de espera
            current_time = datetime.now()
            created_at = current_time.strftime('%Y-%m-%d %H:%M:%S')  
            cursor.execute(
                """INSERT INTO vessel_queue 
                (vessel_id, arrival_time, waiting_time, priority_level) 
                VALUES (%s, %s, %s, %s)""",
                (vessel_id, ship_data['arrival_time'].date(), 0, ship_data['priority'])
            )

            
            self.db_connection.commit()
            cursor.close()
            
            logger.info(f"✅ Navio {ship_data['name']} inserido na BD (ID: {vessel_id})")
            return vessel_id
            
        except Exception as e:
            logger.error(f"❌ Erro ao inserir navio: {e}")
            if self.db_connection:
                self.db_connection.rollback()
            return None

    
    def simulate_berth_operation(self, vessel_id, ship_data):
        """Simula uma operação completa no cais"""
        if not self.db_connection:
            return
            
        try:
            cursor = self.db_connection.cursor()
            
            # Seleciona um cais disponível aleatoriamente
            available_berth = random.randint(1, self.berths_count)
            
            # Simula tempos de operação
            start_time = ship_data['arrival_time'] + timedelta(minutes=random.randint(10, 60))
            operation_duration = ship_data['service_duration'] + random.randint(-50, 100)  # Variação realista
            end_time = start_time + timedelta(seconds=operation_duration)
            
            # Atualiza status do cais para ocupado
            cursor.execute(
                """UPDATE berths 
                   SET status = 'occupied', updated_at = %s 
                   WHERE berth_number = %s""",
                (start_time, available_berth)
            )
            
            # Obtém berth_id
            cursor.execute("SELECT berth_id FROM berths WHERE berth_number = %s", (available_berth,))
            berth_id = cursor.fetchone()[0]
            
            # Registra operação
            cursor.execute(
                """INSERT INTO operations 
                   (vessel_id, berth_id, operation_type, start_time, end_time, status) 
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (vessel_id, berth_id, ship_data['operation_type'], 
                 start_time, end_time, 'completed')
            )
            
            # Atualiza tempo de espera na fila
            wait_time = int((start_time - ship_data['arrival_time']).total_seconds())
            cursor.execute(
                """UPDATE vessel_queue 
                   SET waiting_time = %s 
                   WHERE vessel_id = %s""",
                (wait_time, vessel_id)
            )
            cursor.execute(
                "DELETE FROM vessel_queue WHERE vessel_id = %s",
                (vessel_id,)
            )

            
            # Libera o cais
            cursor.execute(
                """UPDATE berths 
                   SET status = 'available', updated_at = %s 
                   WHERE berth_number = %s""",
                (end_time, available_berth)
            )
            
            # Atualiza status alfandegário se necessário
            if ship_data['customs_status'] == 'pending':
                new_status = random.choice(['approved', 'under_review'])
                cursor.execute(
                    """UPDATE customs_clearance 
                       SET status = %s, last_update = %s 
                       WHERE vessel_id = %s""",
                    (new_status, start_time + timedelta(minutes=30), vessel_id)
                )
            
            self.db_connection.commit()
            cursor.close()
            
            logger.info(f"✅ Operação simulada para {ship_data['name']} no cais {available_berth}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao simular operação: {e}")
            if self.db_connection:
                self.db_connection.rollback()

    def generate_historical_data(self, days_back=7, ships_per_day=12):
        """Gera dados históricos para popular a base de dados"""
        if not self.db_connection:
            return
            
        logger.info(f"🔄 Gerando dados históricos para {days_back} dias...")
        
        try:
            for day in range(days_back, 0, -1):
                date = datetime.now() - timedelta(days=day)
                
                # Gera navios para esse dia
                daily_ships = random.randint(ships_per_day-3, ships_per_day+3)
                
                for ship_num in range(daily_ships):
                    # Distribui chegadas ao longo do dia
                    arrival_hour = random.randint(0, 23)
                    arrival_minute = random.randint(0, 59)
                    arrival_time = date.replace(hour=arrival_hour, minute=arrival_minute)
                    
                    # Gera dados do navio
                    ship_data = self.generate_ship_data()
                    ship_data['arrival_time'] = arrival_time
                    ship_data['name'] = f"Historical-{day}-{ship_num+1}"
                    
                    # Insere na base de dados
                    vessel_id = self.insert_vessel_to_db(ship_data)
                    
                    if vessel_id:
                        # Simula operação completa (80% dos navios completam operação)
                        if random.random() < 0.8:
                            self.simulate_berth_operation(vessel_id, ship_data)
                
                logger.info(f"📊 Dia {day} completo: {daily_ships} navios gerados")
            
            logger.info("✅ Dados históricos gerados com sucesso!")
            
        except Exception as e:
            logger.error(f"❌ Erro ao gerar dados históricos: {e}")

    def simulate_real_time_data(self, duration_minutes=60):
        """Simula dados em tempo real por X minutos"""
        logger.info(f"🚢 Iniciando simulação em tempo real por {duration_minutes} minutos...")
        
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        ships_generated = 0
        
        try:
            while datetime.now() < end_time:
                # Gera novo navio com probabilidade baseada no intervalo
                if random.random() < (1/self.new_ship_interval):
                    ship_data = self.generate_ship_data()
                    vessel_id = self.insert_vessel_to_db(ship_data)
                    
                    if vessel_id:
                        ships_generated += 1
                        
                        # 70% dos navios passam por operação completa
                        if random.random() < 0.7:
                            # Simula com pequeno delay
                            ship_data['arrival_time'] = datetime.now() - timedelta(minutes=random.randint(1,10))
                            self.simulate_berth_operation(vessel_id, ship_data)
                
                # Simula eventos de manutenção ocasionais
                if random.random() < 0.01:  # 1% chance por tick
                    self.simulate_maintenance_event()
                
                time.sleep(self.tick_seconds)
            
            logger.info(f"✅ Simulação concluída! {ships_generated} navios gerados em {duration_minutes} minutos")
            
        except KeyboardInterrupt:
            logger.info("⚠️  Simulação interrompida pelo usuário")
            logger.info(f"📊 Total gerado: {ships_generated} navios")

    def simulate_maintenance_event(self):
        """Simula evento de manutenção em um cais"""
        if not self.db_connection:
            return
            
        try:
            cursor = self.db_connection.cursor()
            berth_number = random.randint(1, self.berths_count)
            
            # Coloca cais em manutenção por 5-15 minutos
            maintenance_duration = random.randint(5, 15)
            start_maintenance = datetime.now()
            end_maintenance = start_maintenance + timedelta(minutes=maintenance_duration)
            
            cursor.execute(
                """UPDATE berths 
                   SET status = 'maintenance', updated_at = %s 
                   WHERE berth_number = %s""",
                (start_maintenance, berth_number)
            )
            
            logger.info(f"🔧 Cais {berth_number} em manutenção por {maintenance_duration} minutos")
            
            # Agenda volta à disponibilidade (em aplicação real, seria um job)
            # Aqui simulamos colocando de volta disponível imediatamente para efeito de demo
            time.sleep(2)  # Pequena pausa para simular
            
            cursor.execute(
                """UPDATE berths 
                   SET status = 'available', updated_at = %s 
                   WHERE berth_number = %s""",
                (end_maintenance, berth_number)
            )
            
            self.db_connection.commit()
            cursor.close()
            
        except Exception as e:
            logger.error(f"❌ Erro na simulação de manutenção: {e}")
            if self.db_connection:
                self.db_connection.rollback()

    def get_database_stats(self):
        """Mostra estatísticas da base de dados"""
        if not self.db_connection:
            return
            
        try:
            cursor = self.db_connection.cursor()
            
            # Estatísticas gerais
            cursor.execute("SELECT COUNT(*) FROM vessels")
            total_vessels = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM operations WHERE status = 'completed'")
            completed_operations = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM operations WHERE status = 'active'")
            active_operations = cursor.fetchone()[0]
            
            cursor.execute("SELECT AVG(waiting_time) FROM vessel_queue WHERE waiting_time > 0")
            avg_wait_result = cursor.fetchone()[0]
            avg_wait_time = float(avg_wait_result) if avg_wait_result else 0
            
            # Estatísticas por tipo de operação
            cursor.execute("""
                SELECT operation_type, COUNT(*) 
                FROM operations 
                GROUP BY operation_type
            """)
            operations_by_type = cursor.fetchall()
            
            # Estatísticas por status alfandegário
            cursor.execute("""
                SELECT status, COUNT(*) 
                FROM customs_clearance 
                GROUP BY status
            """)
            customs_stats = cursor.fetchall()
            
            cursor.close()
            
            # Exibe estatísticas
            print("\n" + "="*50)
            print(f"{Fore.CYAN}📊 ESTATÍSTICAS DA BASE DE DADOS{Style.RESET_ALL}")
            print("="*50)
            print(f"🚢 Total de navios: {Fore.YELLOW}{total_vessels}{Style.RESET_ALL}")
            print(f"✅ Operações concluídas: {Fore.GREEN}{completed_operations}{Style.RESET_ALL}")
            print(f"🔄 Operações ativas: {Fore.BLUE}{active_operations}{Style.RESET_ALL}")
            print(f"⏱️  Tempo médio de espera: {Fore.MAGENTA}{avg_wait_time:.1f}s{Style.RESET_ALL}")
            
            print(f"\n{Fore.CYAN}📈 Operações por tipo:{Style.RESET_ALL}")
            for op_type, count in operations_by_type:
                print(f"  {op_type.upper()}: {count}")
            
            print(f"\n{Fore.CYAN}🏛️  Status alfandegário:{Style.RESET_ALL}")
            for status, count in customs_stats:
                color = Fore.GREEN if status == 'approved' else Fore.YELLOW if status == 'under_review' else Fore.RED
                print(f"  {color}{status.upper()}: {count}{Style.RESET_ALL}")
            
            print("="*50)
            
        except Exception as e:
            logger.error(f"❌ Erro ao obter estatísticas: {e}")

 

    def run_simulation(self):
        """Menu principal para executar diferentes tipos de simulação"""
        print(f"{Fore.CYAN}🚢 SIMULADOR DE DADOS PORTUÁRIOS 🚢{Style.RESET_ALL}")
        print("="*50)

        mode = os.getenv("SIMULATION_MODE", None)

        # Se SIMULATION_MODE estiver definido, roda automático e sai
        if mode:
            if mode == "1":
                self.generate_historical_data(7, 12)
            elif mode == "2":
                self.simulate_real_time_data(60)
            elif mode == "3":
                self.get_database_stats()
            elif mode == "4":
                print(f"{Fore.GREEN}🚀 Executando simulação completa...{Style.RESET_ALL}")
                self.generate_historical_data(7, 15)
                self.simulate_real_time_data(30)
                self.get_database_stats()
            else:
                print("👋 Simulação finalizada!")
            return  

        # Caso contrário, roda menu interativo
        try:
            while True:
                choice = input(f"\n{Fore.YELLOW}Escolha uma opção (0-4): {Style.RESET_ALL}")

                if choice == "1":
                    days = int(input("Quantos dias históricos? (padrão: 7): ") or 7)
                    ships_per_day = int(input("Navios por dia? (padrão: 12): ") or 12)
                    self.generate_historical_data(days, ships_per_day)

                elif choice == "2":
                    duration = int(input("Duração em minutos? (padrão: 60): ") or 60)
                    self.simulate_real_time_data(duration)

                elif choice == "3":
                    self.get_database_stats()

                elif choice == "4":
                    print(f"{Fore.GREEN}🚀 Executando simulação completa...{Style.RESET_ALL}")
                    self.generate_historical_data(7, 15)
                    self.simulate_real_time_data(30)
                    self.get_database_stats()

                elif choice == "0":
                    print(f"{Fore.GREEN}👋 Simulação finalizada!{Style.RESET_ALL}")
                    break

                else:
                    print(f"{Fore.RED}❌ Opção inválida!{Style.RESET_ALL}")

        except (KeyboardInterrupt, EOFError):
            print(f"\n{Fore.YELLOW}⚠️  Simulação interrompida ou sem stdin disponível{Style.RESET_ALL}")

        finally:
            if self.db_connection:
                self.db_connection.close()
                print(f"{Fore.GREEN}✅ Conexão com BD fechada{Style.RESET_ALL}")

                    
            

## Exemplo de uso
if __name__ == "__main__":
    simulator = PortDataSimulator()
    simulator.run_simulation()      

 