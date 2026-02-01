import time

MAX_STORAGE = 50.0

def monitor_storage(capture_queue, state, log_func):
    """
    Verwaltet das 50GB Limit und die Handshake-Logik.
    """
    used_storage = 0.0
    
    while True:
        if not capture_queue.empty():
            task = capture_queue.get()
            
            if task["type"] == "FIND":
                if not state["storage_locked"]:
                    # 4K Aufnahme
                    size = 4.5
                    used_storage += size
                    state["storage_locked"] = True
                    log_func("STORAGE", f"4K Video gesichert. Speicher gesperrt (Handshake-Mode).")
                else:
                    # Low-Res Backup
                    size = 0.2
                    used_storage += size
                    log_func("STORAGE", "Warte auf Erdbestätigung. LR-Paket erstellt.")
                    
        # Check für Speicher-Überlauf
        if used_storage > MAX_STORAGE:
            log_func("STORAGE", "CRITICAL: Speicherlimit erreicht!")
            
        time.sleep(1)