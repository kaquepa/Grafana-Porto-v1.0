import psycopg2
import time
from dotenv import load_dotenv, dotenv_values 
import logging, os
from pathlib import Path
from typing import Optional, Union
from datetime import time, datetime 
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[3] 


class DatabaseManager:
    def __init__(self):
        env_file = Path(env_file or Path(__file__).parent / ".env")
        load_dotenv(dotenv_path=env_file)
        self.user: str = os.getenv("POSTGRES_USER")
        self.password: str = os.getenv("POSTGRES_PASSWORD",)
        self.dbname: str = os.getenv("POSTGRES_DB")
        self.host: str = os.getenv("POSTGRES_HOST")
        self.port: int = int(os.getenv("POSTGRES_PORT", 5432))
    
    def connect(self, retries=5, delay=3) -> bool:
        """Estabelece conexão com retry"""
        for i in range(retries):
            try:
                self.connection = psycopg2.connect(
                    dbname=self.dbname,
                    user=self.user,
                    password=self.password,
                    host=self.host,
                    port=self.port
                )
                logger.info("✅ Conectado ao banco de dados PostgreSQL")
                return True
            except Exception as e:
                logger.warning(f"⚠️ Tentativa {i+1}/{retries} falhou: {e}")
                time.sleep(delay)
        
        logger.error("❌ Não foi possível conectar ao banco de dados após várias tentativas")
        self.connection = None
        return False
    
    def is_connected(self) -> bool:
        """Check if database connection is valid"""
        if not self.connection or self.connection.closed:
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception:
            return False
    
    def initialize_database(self) -> bool:
        """Inicializa o banco de dados com estrutura básica se necessário"""
        if not self.is_connected():
            logger.error("❌ Não há conexão com o banco de dados")
            return False
            
        try:
            cursor = self.connection.cursor()
            
            # Verificar tabelas essenciais
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name IN ('vessels', 'berths', 'operations', 'customs_clearance', "vessel_queue)
            """)
            table_count = cursor.fetchone()[0]
               
            
            if table_count < 4:
                logger.warning("⚠️ Tabelas do banco não estão completas. Execute o script SQL de inicialização primeiro.")
                return False
            
            # Verificar e inicializar cais se necessário
            cursor.execute("SELECT COUNT(*) FROM berths")
            berth_count = cursor.fetchone()[0]
            last_updated = datetime.now()
            
            if berth_count == 0:
                berth_data = [
                    ('Cais 1', 'available', last_updated),
                    ('Cais 2', 'available', last_updated),
                    ('Cais 3', 'available', last_updated),
                    ('Cais 4', 'available', last_updated)
                ]
                
                for berth_number, status in berth_data:
                    cursor.execute(
                        "INSERT INTO berths (berth_number, status) VALUES (%s, %s)",
                        (berth_number, status)
                    )
                
                self.connection.commit()
                logger.info("✅ Cais inicializados no banco de dados")
            
            cursor.close()
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar banco de dados: {e}")
            if self.connection:
                self.connection.rollback()
            return False
    
    def execute_query(self, query, params=None):
        """Executa uma query no banco de dados"""
        if not self.is_connected():
            logger.error("❌ Não há conexão com o banco de dados")
            return None
            
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params or ())
            result = cursor.fetchall() if cursor.description else None
            self.connection.commit()
            cursor.close()
            return result
        except Exception as e:
            logger.error(f"❌ Erro ao executar query: {e}")
            if self.connection:
                self.connection.rollback()
            return None
    
    def close(self):
        """Fecha a conexão com o banco de dados"""
        if self.connection and not self.connection.closed:
            self.connection.close()
            logger.info("✅ Conexão com o banco de dados fechada")
            self.connection = None