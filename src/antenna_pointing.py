import time
import torch
from datetime import datetime

# Hier würde dein DishNet importiert werden
# from train7 import DishNet

def run_loop(state, log_func):
    """
    Hält die Antenne permanent auf die Erde ausgerichtet.
    Nutzt Inferenz um Drift auszugleichen.
    """
    log_func("POINTING", "Autonome Ausrichtung gestartet.")
    while True:
        # Simulierter Inferenz-Schritt zur Erd-Verfolgung
        # Hier käme dein predict_optimal_alignment Code rein
        state["current_az"] = (state["current_az"] + 0.0001) % 360.0
        
        # In der Realität: Ansteuerung der Plasma-Thruster
        time.sleep(2)  # Wartezeit zwischen den Anpassungen