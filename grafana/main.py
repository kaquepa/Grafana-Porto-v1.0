import pandas as pd
from datetime import datetime
import random 
from collections import deque

data = {"Nome": "Graciano", "Pais": "Angola", "Altura": 1.8}
df = pd.DataFrame([data])

print(data.get("Nome"))

 

import random
from datetime import datetime, timedelta

import random
from datetime import datetime, timedelta

# Simulação
arrival_time = datetime.now() - timedelta(minutes=random.randint(0, 120))
start_time = datetime.now()

# Duração da operação com variação aleatória (25-35 segundos, limitada a 1-60)
operation_seconds = max(1, min(60, 30 + random.randint(-5, 5)))
operation_duration = timedelta(seconds=operation_seconds)

end_time = start_time + operation_duration
wait_time = start_time - arrival_time

# Converter para formato HH:MM:SS
def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


 
print(f"Tempo de espera: {format_timedelta(wait_time)}")








class MovingAverage:
    """
    A class to calculate the moving average of a stream of integers.
    Uses a circular buffer to maintain a sliding window of the most recent values.
    """

    def __init__(self, size: int):
        """
        Initialize the MovingAverage with a fixed window size.

        Args:
            size: The size of the moving average window
        """
        self.window_sum = 0  # Running sum of values in the current window
        self.window = [0] * size  # Circular buffer to store window values
        self.count = 0  # Total number of values seen so far

    def next(self, val: int) -> float:
        """
        Add a new value to the stream and return the current moving average.

        Args:
            val: The new integer value to add to the stream

        Returns:
            The moving average of the values in the current window
        """
        # Calculate the index in the circular buffer
        index = self.count % len(self.window)
      
        # Update the running sum by removing the old value and adding the new one
        self.window_sum += val - self.window[index]
      
        # Store the new value in the circular buffer
        self.window[index] = val
      
        # Increment the total count
        self.count += 1
      
        # Calculate average based on actual window size (handles initial filling)
        window_size = min(self.count, len(self.window))
        return self.window_sum / window_size


# Exemplo de uso
if __name__ == "__main__":
    # Criar uma instância com janela de tamanho 3
    ma = MovingAverage(10)
    
    # Testar com alguns valores
    valores = [i for i in range(1, 1000)]  # Valores de 1 a 10 milhões
    
    for valor in valores:
        media = ma.next(valor)
        print(f"Valor adicionado: {valor}, Média móvel: {media}")


