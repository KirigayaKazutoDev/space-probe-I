import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
from datetime import datetime

# ----------------------------
# Config
# ----------------------------
NUM_POSITIONS = 11520  # 0,03125° Schritte für Azimut
EPOCHS = 500
LR = 0.001
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
REG_WEIGHT = 0.5  # Gewicht für den Regressionsanteil im kombinierten Loss (0..1)

# ----------------------------
# Simple Neural Net Model (mit Klassifikation + Regressionsausgang)
# ----------------------------
class DishNet(nn.Module):
    def __init__(self, input_dim, hidden_dim, output_dim):
        super(DishNet, self).__init__()
        # gemeinsamer Encoder
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.act1 = nn.ReLU()
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.act2 = nn.ReLU()
        # Klassifikationskopf (Logits für NUM_POSITIONS Klassen)
        self.class_head = nn.Linear(hidden_dim, output_dim)
        # Regressionskopf (ein skalarer Wert, Normalisiert in [0,1] idealerweise)
        self.reg_head = nn.Linear(hidden_dim, 1)

    def forward(self, x):
        h = self.act1(self.fc1(x))
        h = self.act2(self.fc2(h))
        logits = self.class_head(h)            # (B, NUM_POSITIONS)
        reg = torch.sigmoid(self.reg_head(h))  # (B, 1) -> in (0,1) via Sigmoid
        return logits, reg.squeeze(-1)         # reg: (B,)

# ----------------------------
# Planet/Datum Features (erweitert)
# ----------------------------
def get_planet_position_features():
    """
    Erweiterte planetare Features:
    - Jahresfortschritt Erde
    - Tageszeit (UTC)
    - Lokaler Stundenwinkel (vereinfacht)
    - Mars Umlaufwinkel (~687 Tage)
    - Sonnenwinkel Erde
    - Sonnenwinkel Mars
    - Sichtbarkeit Mars (0/1)
    """
    now = datetime.utcnow()

    # Erdbezogen
    day_of_year = now.timetuple().tm_yday / 365.0
    hour_of_day = now.hour / 24.0
    local_hour_angle = hour_of_day  # stark vereinfacht

    # Mars Umlauf
    mars_angle = ((day_of_year * 360.0 / 687.0) % 360) / 360.0

    # Sonnenwinkel Erde/Mars (stark vereinfacht)
    sun_earth_angle = (day_of_year * 360.0 / 365.0) / 360.0
    sun_mars_angle = mars_angle

    # Sichtbarkeit: Mars über "Horizont" (vereinfachte Näherung)
    visibility = 1.0 if 0.25 <= (local_hour_angle + mars_angle) % 1.0 <= 0.75 else 0.0

    return [day_of_year, hour_of_day, local_hour_angle,
            mars_angle, sun_earth_angle, sun_mars_angle, visibility]

# ----------------------------
# Generate Synthetic Training Data
# ----------------------------
def generate_data(num_samples=64000):
    data = []
    labels = []
    reg_targets = []  # kontinuierlicher Azimut in [0,1]

    MAX_FREQ = 20.0
    MAX_BW = 5.0
    MAX_SNR = 20.0
    MAX_DOPPLER = 1000.0
    MAX_NOISE = 10.0

    for _ in range(num_samples):
        target_azimuth = random.uniform(0, 360)
        target_elevation = random.uniform(0, 90)
        object_type = random.randint(0, 3)

        # TODO: trying to update to case
        if object_type == 0:
            frequency = random.uniform(8.0, 8.5)
            bandwidth = random.uniform(0.1, 0.5)
            snr = random.uniform(0.1, 1.0)
            doppler = random.uniform(-100, 100)
            polarization = random.choice([0.0, 1.0])
            pulse_period = 0.0
            signal_type = 0
            noise_level = random.uniform(0.5, 2.0)
        elif object_type == 1:
            frequency = random.uniform(2.0, 3.0)
            bandwidth = random.uniform(0.01, 0.05)
            snr = random.uniform(0.5, 2.0)
            doppler = random.uniform(-50, 50)
            polarization = random.uniform(-1.0, 1.0)
            pulse_period = 0.0
            signal_type = 0
            noise_level = random.uniform(1.0, 4.0)
        elif object_type == 2:
            frequency = random.uniform(12.0, 18.0)
            bandwidth = random.uniform(1.0, 5.0)
            snr = random.uniform(5.0, 20.0)
            doppler = random.uniform(-200, 200)
            polarization = random.choice([-1.0, 1.0])
            pulse_period = 0.0
            signal_type = 1
            noise_level = random.uniform(0.1, 1.0)
        else:
            frequency = random.uniform(0.1, 1.0)
            bandwidth = random.uniform(0.01, 0.05)
            snr = random.uniform(0.1, 0.5)
            doppler = random.uniform(-50, 50)
            polarization = random.uniform(-1.0, 1.0)
            pulse_period = random.uniform(0.001, 4.0)
            signal_type = 0
            noise_level = random.uniform(5.0, 10.0)

        # Normalisierung
        norm_az = target_azimuth / 360.0
        norm_el = target_elevation / 90.0
        norm_freq = frequency / MAX_FREQ
        norm_bw = bandwidth / MAX_BW
        norm_snr = snr / MAX_SNR
        norm_doppler = (doppler + MAX_DOPPLER) / (2 * MAX_DOPPLER)
        norm_polarization = (polarization + 1.0) / 2.0
        norm_pulse_period = pulse_period / 4.0
        norm_noise = noise_level / MAX_NOISE

        label = int(round(target_azimuth * 32)) % 11520  # Klassenziel (Index)
        reg_target = target_azimuth / 360.0  # Regressionsziel in [0,1]

        # Planet/Datum Features anhängen
        planet_features = get_planet_position_features()

        data.append([norm_az, norm_el, norm_freq, norm_bw, norm_snr, norm_doppler,
                     norm_polarization, norm_pulse_period, signal_type, norm_noise,
                     *planet_features])
        labels.append(label)
        reg_targets.append(reg_target)

    return (torch.tensor(data, dtype=torch.float32),
            torch.tensor(labels, dtype=torch.long),
            torch.tensor(reg_targets, dtype=torch.float32))

# ----------------------------
# Training Function (kombinierter Loss)
# ----------------------------
def train_model():
    model = DishNet(input_dim=17, hidden_dim=256, output_dim=NUM_POSITIONS).to(DEVICE) # hidden_dim=128
    optimizer = optim.Adam(model.parameters(), lr=LR)
    criterion_ce = nn.CrossEntropyLoss()
    criterion_reg = nn.SmoothL1Loss()

    backup_model = DishNet(input_dim=17, hidden_dim=256, output_dim=NUM_POSITIONS).to(DEVICE) # hidden_dim=128
    backup_optimizer = optim.Adam(backup_model.parameters(), lr=LR)

    # Daten: Achtung: hier rufst du mit 32000 auf (primary/backup trainieren beide auf dem selben batch unten)
    X, y, y_reg = generate_data(32000)
    X, y, y_reg = X.to(DEVICE), y.to(DEVICE), y_reg.to(DEVICE)

    for epoch in range(EPOCHS):
        model.train()
        optimizer.zero_grad()
        out_logits, out_reg = model(X)  # out_logits: (B, NUM_POSITIONS), out_reg: (B,)

        loss_ce = criterion_ce(out_logits, y)
        loss_reg = criterion_reg(out_reg, y_reg)
        loss = (1.0 - REG_WEIGHT) * loss_ce + REG_WEIGHT * loss_reg

        loss.backward()
        optimizer.step()

        print(f"Epoch {epoch+1}/{EPOCHS}, Primary Model Loss: {loss.item():.4f} (CE={loss_ce.item():.4f}, REG={loss_reg.item():.4f})")

        if loss.item() > 5.5:
            print("Anomaly detected in primary model. Backup system engaged...")
            backup_model.train()
            backup_optimizer.zero_grad()
            out_logits_b, out_reg_b = backup_model(X)
            loss_ce_b = criterion_ce(out_logits_b, y)
            loss_reg_b = criterion_reg(out_reg_b, y_reg)
            loss_backup = (1.0 - REG_WEIGHT) * loss_ce_b + REG_WEIGHT * loss_reg_b
            loss_backup.backward()
            backup_optimizer.step()
            combined_loss_display = (loss.item() + loss_backup.item()) / 2
            print(f"Combined loss: {combined_loss_display:.4f}")

        if epoch % 2 == 0:
            try:
                torch.save({
                    'model_state_dict': model.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict(),
                }, "model_with_optimizer.pt")

                torch.save({
                    'model_state_dict': backup_model.state_dict(),
                    'optimizer_state_dict': backup_optimizer.state_dict(),
                }, "backup_model_with_optimizer.pt")
                print("Primary and Backup models with optimizers saved successfully.")
            except Exception as e:
                print(f"Error while saving models: {e}")

    return model, optimizer, backup_model, backup_optimizer

# ----------------------------
# Inference Function (kombiniert: logits + regression)
# ----------------------------
def predict_position(model, azimuth, elevation, frequency, bandwidth, snr, doppler, polarization, pulse_period, signal_type, noise_level):
    """
    Liefert einen kontinuierlichen Azimut in Grad (float).
    Kombiniert die Logits-basierte Erwartungswert-Schätzung mit dem Regressionsausgang,
    gewichtet nach der Peak-Wahrscheinlichkeit der Softmax-Verteilung.
    """
    model.eval()
    with torch.no_grad():
        MAX_DOPPLER = 1000.0
        MAX_NOISE = 10.0
        norm_az = azimuth / 360.0
        norm_el = elevation / 90.0
        norm_freq = frequency / 20.0
        norm_bw = bandwidth / 5.0
        norm_snr = snr / 20.0
        norm_doppler = (doppler + MAX_DOPPLER) / (2 * MAX_DOPPLER)
        norm_polarization = (polarization + 1.0) / 2.0
        norm_pulse_period = pulse_period / 4.0
        norm_noise = noise_level / MAX_NOISE

        planet_features = get_planet_position_features()

        inp = torch.tensor([[norm_az, norm_el, norm_freq, norm_bw, norm_snr, norm_doppler,
                             norm_polarization, norm_pulse_period, signal_type, norm_noise,
                             *planet_features]],
                           dtype=torch.float32).to(DEVICE)

        out_logits, out_reg = model(inp)  # out_reg in (0,1)
        # Logits -> Wahrscheinlichkeiten -> Erwartungsindex
        probs = torch.softmax(out_logits, dim=1)  # (1, N)
        idxs = torch.arange(probs.shape[1], dtype=torch.float32, device=probs.device)
        expected_idx = (probs * idxs).sum(dim=1).item()  # scalar
        deg_per_index = 360.0 / float(NUM_POSITIONS)
        deg_from_logits = expected_idx * deg_per_index

        deg_from_reg = float(out_reg.item() * 360.0)  # Regressionsausgang -> Grad

        peak_prob = float(probs.max().item())

        # Gewichtete Kombination: je sicherer die Klassifikation (peak_prob), desto mehr Gewicht für logits-basierte Schätzung
        final_deg = peak_prob * deg_from_logits + (1.0 - peak_prob) * deg_from_reg

        # Normalisiere auf [0,360)
        final_deg = final_deg % 360.0

    return final_deg

# ----------------------------
# Example "Dish Control" (mehr Nachkommastellen)
# ----------------------------
def rotate_dish_to(position):
    print(f"Rotating dish to azimuth {position:.5f} degrees")

# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    # Trainiere das Modell
    model, optimizer, backup_model, backup_optimizer = train_model()

    # Beispiel-Inferenz mit Testdaten
    test_azimuth = 300
    test_elevation = 45
    test_frequency = 15.0
    test_bandwidth = 2.5
    test_snr = 10.0
    test_doppler = 150.0
    test_polarization = 1.0
    test_pulse_period = 0.0
    test_signal_type = 1
    test_noise_level = 0.5

    # Vorhersage der besten Position
    best_pos = predict_position(model, test_azimuth, test_elevation, test_frequency,
                                test_bandwidth, test_snr, test_doppler, test_polarization,
                                test_pulse_period, test_signal_type, test_noise_level)
    print(f"Predicted best position: {best_pos:.5f} degrees")

    rotate_dish_to(best_pos)

# TODO: more accurate positions
