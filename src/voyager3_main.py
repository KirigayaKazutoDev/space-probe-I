import threading
import time
import queue
from datetime import datetime

# Import der spezialisierten Module
import antenna_pointing
import ai_scanner
import storage_manager
import comms_handler

class Voyager3Control:
    def __init__(self):
        self.is_active = True
        self.shared_state = {
            "current_az": 0.0,
            "current_el": 45.0,
            "storage_locked": False,
            "ai_active": True,
            "last_signal_snr": 0.0
        }
        
        # Kommunikation zwischen Modulen via Queues
        self.command_queue = queue.Queue()
        self.data_capture_queue = queue.Queue()

    def log(self, system, message):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{system}] {message}")

    def run(self):
        self.log("CORE", "Initialisiere Voyager 3 Betriebssystem...")
        
        # 1. Antennen-Ausrichtung starten (Priorität 1)
        pointing_thread = threading.Thread(
            target=antenna_pointing.run_loop, 
            args=(self.shared_state, self.log),
            daemon=True
        )
        
        # 2. KI-Scanner starten (Priorität 2)
        scanner_thread = threading.Thread(
            target=ai_scanner.run_inference_loop, 
            args=(self.shared_state, self.data_capture_queue, self.log),
            daemon=True
        )
        
        # 3. Speicher-Manager starten
        storage_thread = threading.Thread(
            target=storage_manager.monitor_storage, 
            args=(self.data_capture_queue, self.shared_state, self.log),
            daemon=True
        )

        # 4. Comms-Handler (Empfang von der Erde)
        comms_thread = threading.Thread(
            target=comms_handler.listen_for_earth, 
            args=(self.command_queue, self.shared_state, self.log),
            daemon=True
        )

        # Startet alle Systeme
        pointing_thread.start()
        scanner_thread.start()
        storage_thread.start()
        comms_thread.start()

        self.log("CORE", "Alle Module online. Antimaterie-Reaktor stabil.")

        try:
            while self.is_active:
                # Verarbeitet Kommandos von der Erde
                if not self.command_queue.empty():
                    cmd = self.command_queue.get()
                    self.process_system_command(cmd)
                time.sleep(1)
        except KeyboardInterrupt:
            self.log("CORE", "Shutdown eingeleitet.")

    def process_system_command(self, cmd):
        if cmd == "ack_delete":
            self.shared_state["storage_locked"] = False
            self.log("CORE", "Speicher-Handshake erfolgreich. Slot freigegeben.")
        elif cmd == "scan_off":
            self.shared_state["ai_active"] = False
        elif cmd == "scan_on":
            self.shared_state["ai_active"] = True

if __name__ == "__main__":
    voyager = Voyager3Control()
    voyager.run()