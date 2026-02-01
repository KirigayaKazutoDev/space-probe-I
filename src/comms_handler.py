import time
import random
import hashlib

def verify_secret_code(received_code, expected_hash):
    """
    Überprüft den empfangenen Code gegen einen kryptografischen Hash.
    Verhindert Hijacking der Sonde durch unbefugte Signale.
    """
    check_hash = hashlib.sha256(received_code.encode()).hexdigest()
    return check_hash == expected_hash

def listen_for_earth(cmd_queue, state, log_func):
    """
    Hört auf eingehende Funksignale von der Erde (Deep Space Network).
    Diese Signale sind nur empfangbar, wenn das Dish-Pointing (KI) korrekt ist.
    """
    # Autorisierte Befehlshashes (SHA-256)
    # Diese Hashes entsprechen geheimen Passwörtern, die nur die Bodenstation kennt
    CODES = {
        "8f683e896930594382583204787a2d677a83d98045b85e0543f443588a4e8248": "ack_delete", 
        "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8": "scan_off",    
        "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d": "scan_on"      
    }

    log_func("COMMS", "Radio-Empfänger aktiv. Suche Trägerwelle auf Erdfrequenz...")

    while True:
        # 1. Die Pointing-Abhängigkeit:
        # Wir prüfen, wie genau die Antenne (aus dem Pointing-Modul) ausgerichtet ist.
        # Ziel-Azimut für Erde ist ca. 300.0° (Referenzwert für dieses Szenario)
        pointing_error = abs(state.get("current_az", 0) - 300.0)
        
        # Link-Qualität berechnen (simuliert den SNR-Input für deine Dish-KI)
        # Je kleiner der Fehler (dank deiner DishNet KI), desto besser der Empfang
        if pointing_error < 0.05: # Sehr präzise Ausrichtung
            state["link_quality"] = random.uniform(95.0, 99.9)
            can_receive = True
        elif pointing_error < 0.5:
            state["link_quality"] = random.uniform(40.0, 70.0)
            can_receive = random.random() > 0.5 # Instabiler Empfang bei Drift
        else:
            state["link_quality"] = random.uniform(0.0, 5.0)
            can_receive = False

        # 2. Signalverarbeitung & Lichtlaufzeit
        # Im tiefen Weltraum dauert es Sekunden bis Minuten, ein Paket zu synchronisieren
        time.sleep(10) 

        if can_receive:
            # Wenn der Speicher gesperrt ist (Warten auf Handshake), suchen wir aktiv nach dem ACK
            if state.get("storage_locked", False) and random.random() > 0.8:
                log_func("COMMS", f"Signal stabil (SNR: {state['link_quality']:.1f}). Dekodiere DSN-Paket...")
                
                # Simulierter Payload von der Bodenstation
                received_payload = "voyager_confirm_2025" 
                payload_hash = hashlib.sha256(received_payload.encode()).hexdigest()
                
                if payload_hash in CODES:
                    cmd = CODES[payload_hash]
                    log_func("COMMS", f"Authentifizierter Befehl empfangen: {cmd}")
                    # Befehl an den Main-Orchestrator weiterleiten
                    cmd_queue.put(cmd)
                else:
                    log_func("COMMS", "Fehler: Prüfsumme ungültig oder unbefugter Zugriffscode detektiert.")
        else:
            # Visuelles Feedback für den User, wenn das Pointing wegläuft
            if state.get("storage_locked", False):
                log_func("COMMS", "WARNUNG: Verbindungsabbruch. Dish-Ausrichtung korrigieren!")

        # Kurze Pause für den nächsten Scan-Zyklus
        time.sleep(5)