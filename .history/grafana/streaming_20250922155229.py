from datetime import datetime, time, timedelta, timezone
import psycopg2
import logging
import random
import os
import time 
from colorama import init, Fore, Style
from tabulate import tabulate

# Inicializar colorama
init(autoreset=True)

# CONFIGURAR LOGGING CORRETAMENTE
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Para console
        logging.FileHandler('port_simulator.log')  # Para arquivo
    ]
)
logger = logging.getLogger(__name__)

class PortDataSimulator:
    def __init__(self, berths_count=4, tick_seconds=5, new_ship_interval=20):
        self.berths_count = berths_count
        self.berths = [None] * berths_count
        self.waiting_queue = []
        self.tick_seconds = tick_seconds
        self.new_ship_interval = new_ship_interval
        self.last_ship_time = datetime.now()
        self.ship_counter = 0
        self.duration_seconds = 0

        # Estatísticas para simulação
        self.total_ships_handled = 0
        self.total_wait_time = 0
        self.total_service_time = 0
        self.berth_occupancy_time = [0] * berths_count
        self.start_time = datetime.now()
        self.history = []
        self.events = []

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
                        "INSERT INTO berths (berth_number, status, start_maintenance,end_maintenance ) VALUES (%s, %s,%s, %s)",
                        (i, 'available', None, None)
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
            ("Cargueiro", 1, (30, 60), "import"),
            ("Porta-Container", 2, (40, 80), "import"), 
            ("Tanker", 3, (50, 90), "import"),
            ("Bulk Carrier", 1, (3, 70), "export"),
            ("RoRo", 2, (20, 40), "export"),
            ("Frigorífico", 3, (45, 55), "import")
        ]
        
        ship_type, priority, duration_range, operation = random.choice(ship_types)
        # Gerar service_duration corretamente como timedelta
        service_seconds = random.randint(45, 120)
  
        
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
            'service_duration': timedelta(seconds=service_seconds),         #timedelta( minutes=random.randint(0, 60)),      #   service_duration,
            'operation_type': operation,
            'customs_status': customs_status,
            'arrival_time': datetime.now() - timedelta(minutes=random.randint(5, 120)) # Gera tempo de chegada entre 5 minutos e 2 horas atrás
        }

    def insert_vessel_to_db(self, ship_data):
        """Insere dados do navio na base de dados"""
        if not self.db_connection:
            return None
            
        try:
            cursor = self.db_connection.cursor()
            
            # Inserir navio na tabela vessels
            # Calcular quando o serviço vai terminar (TIMESTAMP)
            service_duration_timedelta = ship_data['service_duration']
            self.duration_seconds = int(service_duration_timedelta.total_seconds())

            #logger.info(f"service_duration: {service_duration_timedelta} -> {self.duration_seconds} segundos")



            cursor.execute(
                """INSERT INTO vessels 
                   (vessel_name, vessel_type, priority, estimated_duration) 
                   VALUES (%s, %s, %s, %s) 
                   RETURNING vessel_id""",
                (ship_data['name'], ship_data['type'], 
                 ship_data['priority'], self.duration_seconds )
            )
            vessel_id = cursor.fetchone()[0]
            
            #logger.info(f"🚢 🚢🚢🚢🚢🚢🚢🚢 Novo navio gerado: {ship_data['name']} (service_duration: {ship_data['service_duration']})\n"  )



            # Inserir dados alfandegários
            cursor.execute(
                """INSERT INTO customs_clearance 
                   (vessel_id, status) 
                   VALUES (%s, %s)""",
                (vessel_id, ship_data['customs_status'])
            )
            
            # Inserir na fila de espera
            cursor.execute(
                """INSERT INTO vessel_queue 
                   (vessel_id, arrival_time) 
                   VALUES (%s, %s)""",
                (vessel_id, ship_data['arrival_time'] ) #, ship_data['priority']
            )
            
            self.db_connection.commit()
            cursor.close()
            
            #logger.info(f"✅ Navio {ship_data['name']} inserido na BD (ID: {vessel_id})")
            return vessel_id
            
        except Exception as e:
            logger.error(f"❌ Erro ao inserir navio: {e}")
            if self.db_connection:
                self.db_connection.rollback()
            return None


























































    def allocate_ships_to_berths(self):
        """Aloca navios da fila aos cais disponíveis, registrando operações e atualizando tempos de espera."""
        if not self.db_connection:
            logger.warning("❌ Conexão com o banco de dados não disponível")
            return
            
        try:
            cursor = self.db_connection.cursor()
            
            # 1️⃣ Checar navios na fila
            cursor.execute("SELECT COUNT(*) FROM vessel_queue WHERE status = 'waiting'")
            num_ships = cursor.fetchone()[0]
            if num_ships == 0:
                #logger.info("⚠️ Nenhum navio na fila no momento")
                return
                
            # Buscar todos os cais disponíveis
            cursor.execute("SELECT berth_id, berth_number FROM berths WHERE status = 'available'")
            available_berths = cursor.fetchall()
            if not available_berths:
                #logger.info("⚠️ Nenhum cais disponível no momento")
                return
                
            for berth_id, berth_number in available_berths:
                # Selecionar o próximo navio na fila (maior prioridade, chegada mais antiga)
                cursor.execute("""
                     SELECT vq.vessel_id, v.vessel_name, v.priority, 
                       v.estimated_duration, vq.arrival_time
                        FROM vessel_queue vq
                        JOIN vessels v ON vq.vessel_id = v.vessel_id
                        WHERE vq.status = 'waiting'
                        ORDER BY v.priority DESC, vq.arrival_time ASC
                        LIMIT 1
                """)
                ship = cursor.fetchone()
                if not ship:
                    continue  # Nenhum navio na fila
                    
                vessel_id, vessel_name, priority, estimated_completion_time, arrival_time = ship
                
                start_time = datetime.now()
                # Calcular end_time baseado na duração em segundos
                end_time = start_time + timedelta(seconds=self.duration_seconds)

                # Calcular tempo de espera REAL (quanto tempo esperou até ser atendido)
                wait_time_seconds = int((start_time - arrival_time).total_seconds())

                
                # Atualizar fila: marcar como em serviço e registrar tempo de espera
                cursor.execute( """ 
                    UPDATE vessel_queue 
                            SET start_service_time = %s,
                            status = 'in_service'
                    WHERE vessel_id = %s""",
                    (start_time, vessel_id)  
                )
                
                # Marcar cais como ocupado
                cursor.execute(
                    "UPDATE berths SET status = 'occupied', updated_at = %s WHERE berth_id = %s",
                    (start_time, berth_id)
                )
                
                # Registrar operação
                operation_type = random.choice(["import", "export"])
                cursor.execute("""
                    INSERT INTO operations (vessel_id, berth_id, operation_type, start_time, end_time, status, planned_duration)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (vessel_id, berth_id, operation_type, start_time, end_time, 'in_progress', self.duration_seconds))
                
                # Remover navio da fila
                #cursor.execute("DELETE FROM vessel_queue WHERE vessel_id = %s", (vessel_id,))
                
                logger.info(f"✅ Navio {vessel_name} alocado ao cais {berth_number} - Espera: {wait_time_seconds}s")
                
            self.db_connection.commit()
            cursor.close()
            
        except Exception as e:
            logger.error(f"❌ Erro ao alocar navios: {e}")
            if self.db_connection:
                self.db_connection.rollback()
   
  




    def simulate_real_time_data(self):
        ships_generated = 0
        try:
            # Primeiro, libera cais cuja manutenção já terminou
            self.release_maintenance_berths()
            while True: #datetime.now() < end_time:
                # Gera novo navio com probabilidade baseada no intervalo
                _random = random.choices([0,1], weights=[40, 60])[0]
                if _random == 0:
                    ship_data = self.generate_ship_data()
                    vessel_id = self.insert_vessel_to_db(ship_data)
                    
                    if vessel_id:
                        ships_generated += 1
                
                # ***PRIMEIRO atualiza operações (libera cais)
                self.update_ongoing_operations()


                # ⭐⭐ NOVO: Finalizar operações completadas ⭐⭐
           

                # Libera cais cuja manutenção já terminou
                self.release_maintenance_berths()
        
                #  aloca navios aos cais disponíveis
                self.allocate_ships_to_berths()
                
                # Simula eventos de manutenção ocasionais
                if random.random() < 0.3:  # 30% chance por tick
                    self.simulate_maintenance_event()
                time.sleep(self.tick_seconds)
        except KeyboardInterrupt:
            logger.info("⚠️  Simulação interrompida pelo usuário")
            logger.info(f"📊 Navios gerados: {ships_generated} | Navios processados: {self.total_ships_handled}")

    def simulate_maintenance_event(self):
        """Simula evento de manutenção em um cais"""
        if not self.db_connection:
            return

        try:
            cursor = self.db_connection.cursor()

            # Seleciona cais disponível
            cursor.execute(
                "SELECT berth_id, berth_number FROM berths WHERE status = 'available' ORDER BY RANDOM() LIMIT 1"
            )
            berth_result = cursor.fetchone()

            if not berth_result:
                return  # Nenhum cais disponível

            berth_id, berth_number = berth_result

            # Duração da manutenção (5 a 10 min)
            maintenance_duration = random.randint(5, 10)
            start_maintenance = datetime.now()
            end_maintenance = start_maintenance + timedelta(minutes=maintenance_duration)

            # Atualiza status para 'maintenance' com horários
            cursor.execute("""
                UPDATE berths
                SET status = 'maintenance',
                    start_maintenance = %s,
                    end_maintenance = %s,
                    updated_at = %s
                WHERE berth_id = %s AND status = 'available'
            """, (start_maintenance, end_maintenance, start_maintenance, berth_id))

            self.db_connection.commit()
            logger.info(f"🔧 Cais {berth_number} em manutenção por {maintenance_duration} minutos")

            cursor.close()

        except Exception as e:
            logger.error(f"❌ Erro na simulação de manutenção: {e}")
            if self.db_connection:
                self.db_connection.rollback()

    def release_maintenance_berths(self):
        """Libera cais cuja manutenção já terminou"""
        if not self.db_connection:
            return

        try:
            cursor = self.db_connection.cursor()
            now = datetime.now()

            cursor.execute("""
                UPDATE berths
                SET status = 'available',
                    updated_at = %s,
                    start_maintenance = %s,
                    end_maintenance = %s
                WHERE status = 'maintenance' AND end_maintenance <= %s
                RETURNING berth_number
            """, (now, None, None, now))

            released = cursor.fetchall()
            self.db_connection.commit()
            cursor.close()

            for berth_number, in released:
                logger.info(f"✅ Cais {berth_number} liberado após manutenção")

        except Exception as e:
            logger.error(f"❌ Erro ao liberar cais: {e}")
            if self.db_connection:
                self.db_connection.rollback()

    def update_ongoing_operations(self):
        """Atualiza operações em andamento e libera cais concluídos"""
        if not self.db_connection:
            return
            
        try:
            cursor = self.db_connection.cursor()
            current_time = datetime.now(timezone.utc)
            
            # Verificar operações que devem ser finalizadas
            cursor.execute(
                """SELECT o.operation_id, o.berth_id, o.vessel_id, o.start_time, o.planned_duration, v.vessel_name, b.berth_number
                FROM operations o
                JOIN vessels v ON o.vessel_id = v.vessel_id
                JOIN berths b ON o.berth_id = b.berth_id
                WHERE o.status = 'in_progress' AND o.end_time <= %s""",
                (current_time,)
            )
            
            completed_operations = cursor.fetchall()
            
            for op_id, berth_id, vessel_id, start_time, planned_duration,  vessel_name, berth_number in completed_operations:
                # 1. Finalizar operação (APENAS atualizar status)
                actual_duration = int((current_time - start_time).total_seconds())

                cursor.execute(
                    "UPDATE operations SET status = 'completed', actual_duration = %s WHERE operation_id = %s",
                    (actual_duration, op_id)
                )
                
                # 2. Liberar cais (APENAS mudar status)
                cursor.execute(
                    """UPDATE berths 
                    SET status = 'available', updated_at = %s 
                    WHERE berth_id = %s""",
                    (current_time, berth_id)
                )
                
                # 3. Atualizar fila para 'completed' (NÃO APAGAR)
                cursor.execute(
                    """UPDATE vessel_queue 
                    SET status = 'completed', end_service_time = %s
                    WHERE vessel_id = %s""",
                    (current_time, vessel_id)
                )
                
                # 4. MANTER todos os dados para histórico!
                # NÃO APAGAR vessels, customs_clearance, etc!
                
                # Incrementar contador de navios processados
                self.total_ships_handled += 1


                # 5. Calcular eficiência para logging
                efficiency = round((planned_duration / actual_duration) * 100, 2) if actual_duration > 0 else 0

                
                logger.info(f"🚢 Navio {vessel_name} concluiu operação no cais {berth_number}")
                logger.info(f"⏱️  Duração: {actual_duration}s (Planeado: {planned_duration}s) - Eficiência: {efficiency}%")
                logger.info(f"📊 Total de navios processados: {self.total_ships_handled}")
            
            self.db_connection.commit()
            cursor.close()
                
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar operações: {e}")
            if self.db_connection:
                self.db_connection.rollback()






    def get_database_stats(self):
        """Mostra estatísticas da base de dados - COM CASCADE DELETE"""
        if not self.db_connection:
            return
            
        try:
            cursor = self.db_connection.cursor()
            
            # Navios ATUALMENTE no porto  
            cursor.execute("SELECT COUNT(*) FROM vessels")
            current_vessels = cursor.fetchone()[0]
            
            # Navios na fila de espera (aguardando cais)
            cursor.execute("SELECT COUNT(*) FROM vessel_queue")
            queue_length = cursor.fetchone()[0]
            
            # Operações ativas  
            cursor.execute("SELECT COUNT(*) FROM operations WHERE status = 'in_progress'")
            active_operations = cursor.fetchone()[0]
            
            # Total de operações já concluídas (representa navios que já partiram)
            # Como usamos CASCADE DELETE, não temos mais os vessels, mas temos o histórico em operations
            cursor.execute("SELECT COUNT(*) FROM operations WHERE status = 'completed'")
            completed_operations = cursor.fetchone()[0]
            
            # Tempo médio de espera na fila (apenas para navios atualmente esperando)
            cursor.execute("SELECT AVG(EXTRACT(EPOCH FROM waiting_time)) FROM vessel_queue WHERE waiting_time > INTERVAL '0 seconds'")
            avg_wait_result = cursor.fetchone()[0]
            avg_wait_time =  float(avg_wait_result) if avg_wait_result else 0
            
            # Status dos cais
            cursor.execute("SELECT COUNT(*) FROM berths WHERE status = 'available'")
            available_berths = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM berths WHERE status = 'occupied'")
            occupied_berths = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM berths WHERE status = 'maintenance'")
            maintenance_berths = cursor.fetchone()[0]
            
            # Operações ativas por tipo
            cursor.execute("""
                SELECT o.operation_type, COUNT(*) 
                FROM operations o
                WHERE o.status = 'in_progress'
                GROUP BY o.operation_type
            """)
            active_operations_by_type = cursor.fetchall()
            
            # Estatísticas de throughput (navios por hora nas últimas 24h)
            cursor.execute("""
                SELECT COUNT(*) as ships_last_24h
                FROM operations 
                WHERE status = 'completed' 
                AND start_time >= NOW() - INTERVAL '24 hours'
            """)
            throughput_24h = cursor.fetchone()[0]
            
            cursor.close()
            
            # Exibe estatísticas do fluxo portuário com CASCADE DELETE
            logger.info("\n" + "="*60)
            logger.info(f"{Fore.CYAN}🚢 ESTATÍSTICAS DO FLUXO PORTUÁRIO (CASCADE DELETE){Style.RESET_ALL}")
            logger.info("="*60)
            logger.info(f"📋 Navios na fila de espera: {Fore.YELLOW}{queue_length}{Style.RESET_ALL}")
            logger.info(f"🔄 Navios sendo atendidos: {Fore.BLUE}{active_operations}{Style.RESET_ALL}")
            logger.info(f"🚢 Total navios no porto: {Fore.CYAN}{current_vessels}{Style.RESET_ALL}")
            logger.info(f"✅ Navios já processados (partidos): {Fore.GREEN}{self.total_ships_handled}{Style.RESET_ALL}")
            logger.info(f"📊 Operações concluídas (histórico): {Fore.GREEN}{completed_operations}{Style.RESET_ALL}")
            logger.info(f"⚡ Throughput (24h): {Fore.MAGENTA}{throughput_24h} navios{Style.RESET_ALL}")
            logger.info(f"⏱️  Tempo médio na fila: {Fore.MAGENTA}{avg_wait_time:.1f}s{Style.RESET_ALL}")
            
            logger.info(f"\n{Fore.CYAN}🅿️  STATUS DOS CAIS:{Style.RESET_ALL}")
            logger.info(f"  🟢 Livres: {Fore.GREEN}{available_berths}{Style.RESET_ALL}")
            logger.info(f"  🔴 Ocupados: {Fore.RED}{occupied_berths}{Style.RESET_ALL}")
            logger.info(f"  🟡 Manutenção: {Fore.YELLOW}{maintenance_berths}{Style.RESET_ALL}")
            
          
           
        except Exception as e:
            logger.error(f"❌ Erro ao obter estatísticas: {e}")

    def run_simulation(self):
        # Executa simulação completa
        try:
            time.sleep(10)
            logger.info(f"{Fore.GREEN}🚀 Executando simulação completa...{Style.RESET_ALL}")
            self.simulate_real_time_data()
            self.get_database_stats()
                
        except (KeyboardInterrupt, EOFError):
            logger.error(f"\n{Fore.YELLOW}⚠️  Simulação interrompida{Style.RESET_ALL}")
        finally:
            if self.db_connection:
                self.db_connection.close()
                logger.info(f"{Fore.GREEN}✅ Conexão com BD fechada{Style.RESET_ALL}")

if __name__ == "__main__":
    simulator = PortDataSimulator()
    simulator.run_simulation()