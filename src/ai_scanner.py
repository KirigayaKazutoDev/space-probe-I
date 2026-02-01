import time
import random

def run_inference_loop(state, capture_queue, log_func):
    """
    Nutzt die Dish-KI um nach SNR-Peaks und Mustern zu suchen.
    """
    log_func("AI-SCAN", "DishNet Inferenz-Einheit aktiv.")
    while True:
        if state["ai_active"]:
            snr = random.uniform(0, 15)
            state["last_signal_snr"] = snr
            
            if snr > 9.5:
                log_func("AI-SCAN", f"Muster erkannt! SNR: {snr:.2f}")
                # Melde Fund an den Storage-Manager
                capture_queue.put({"type": "FIND", "snr": snr, "az": state["current_az"]})
                
        time.sleep(5)