# inference_and_pointing7.py
import torch
import torch.optim as optim
import numpy as np
from math import fmod
from train7 import DishNet, DEVICE, NUM_POSITIONS
from datetime import datetime
import random
import os

PRIMARY_MODEL_PATH = "model_with_optimizer.pt"
BACKUP_MODEL_PATH = "backup_model_with_optimizer.pt"
LR = 0.001  # Nur für Optimizer nötig

# ----------------------------
# Motor Controller
# ----------------------------
class MotorController:
    def __init__(self, dish_id):
        self.dish_id = dish_id
    def move_to(self, az, el):
        print(f"Dish {self.dish_id}: moving to az={az:.5f}, el={el:.5f}")

# ----------------------------
# Planet/Datum Features (wie im Training!)
# ----------------------------
def get_planet_position_features():
    now = datetime.utcnow()
    day_of_year = now.timetuple().tm_yday / 365.0
    hour_of_day = now.hour / 24.0
    local_hour_angle = hour_of_day
    mars_angle = ((day_of_year * 360.0 / 687.0) % 360) / 360.0
    sun_earth_angle = (day_of_year * 360.0 / 365.0) / 360.0
    sun_mars_angle = mars_angle
    visibility = 1.0 if 0.25 <= (local_hour_angle + mars_angle) % 1.0 <= 0.75 else 0.0
    return [day_of_year, hour_of_day, local_hour_angle,
            mars_angle, sun_earth_angle, sun_mars_angle, visibility]

# ----------------------------
# Normalisierung
# ----------------------------
def normalize(az, el, freq, bw, snr, doppler, polarization, pulse_period, signal_type, noise_level):
    MAX_DOPPLER = 1000.0
    MAX_NOISE = 10.0
    base_features = [
        az / 360.0,
        el / 90.0,
        freq / 20.0,
        bw / 5.0,
        snr / 20.0,
        (doppler + MAX_DOPPLER) / (2 * MAX_DOPPLER),
        (polarization + 1.0) / 2.0,
        pulse_period / 4.0,
        signal_type,
        noise_level / MAX_NOISE
    ]
    return np.array(base_features + get_planet_position_features(), dtype=np.float32)

# ----------------------------
# Lade Modell inkl. Optimizer
# ----------------------------
def load_model_with_optimizer(path):
    checkpoint = torch.load(path, map_location=DEVICE)
    model = DishNet(input_dim=17, hidden_dim=256, output_dim=NUM_POSITIONS).to(DEVICE) # hidden_dim=128
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer = optim.Adam(model.parameters(), lr=LR)
    if 'optimizer_state_dict' in checkpoint:
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    model.eval()
    return model, optimizer

# ----------------------------
# Kandidaten erzeugen
# ----------------------------
def generate_candidates(center_az, center_el, grid_deg=4.0, steps=5):
    azs = np.linspace(center_az - grid_deg, center_az + grid_deg, steps)
    els = np.linspace(max(0, center_el - grid_deg), min(90, center_el + grid_deg), steps)
    return [(fmod(a + 360, 360), e) for a in azs for e in els]

# ----------------------------
# Simulierte reale SNR
# ----------------------------
def get_real_snr(az, el, predicted_snr):
    true_az, true_el, true_snr = 300.0, 45.0, 10.0
    distance = np.sqrt((az - true_az)**2 + (el - true_el)**2)
    return true_snr * random.uniform(0.9, 1.1) if distance < 1.0 else predicted_snr * random.uniform(0.5, 0.9)

# ----------------------------
# Hilfsfunktion: kombiniere Logits + Regression
# ----------------------------
def logits_reg_to_deg(out_logits, out_reg):
    probs = torch.softmax(out_logits, dim=1)  # (1, N)
    idxs = torch.arange(probs.shape[1], dtype=torch.float32, device=probs.device)
    expected_idx = (probs * idxs).sum(dim=1).item()
    deg_from_logits = expected_idx * (360.0 / NUM_POSITIONS)
    deg_from_reg = float(out_reg.item() * 360.0)
    peak_prob = float(probs.max().item())
    final_deg = peak_prob * deg_from_logits + (1.0 - peak_prob) * deg_from_reg
    return final_deg % 360.0, peak_prob

# ----------------------------
# Hauptprogramm
# ----------------------------
if __name__ == '__main__':
    model, optimizer = load_model_with_optimizer(PRIMARY_MODEL_PATH)
    backup_model = None
    if os.path.exists(BACKUP_MODEL_PATH):
        backup_model, backup_optimizer = load_model_with_optimizer(BACKUP_MODEL_PATH)
        print("Primary and Backup models loaded with optimizers.")
    else:
        print("Primary model loaded. No backup found.")

    dish = MotorController(dish_id=0)
    coarse_az, coarse_el = 180.0, 45.0
    cands = generate_candidates(coarse_az, coarse_el)

    best, best_score = None, -1.0

    # Simulierte Messwerte
    sim_freq = 15.0
    sim_bw = 2.5
    sim_snr = 10.0
    sim_doppler = 150.0
    sim_pol = 1.0
    sim_pp = 0.0
    sim_sig_type = 1
    sim_noise = 0.5

    primary_weight, backup_weight = 2.0, 1.0

    for az, el in cands:
        feat = normalize(az, el, sim_freq, sim_bw, sim_snr, sim_doppler, sim_pol, sim_pp, sim_sig_type, sim_noise)
        xb = torch.from_numpy(feat).unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            out_logits, out_reg = model(xb)
            prim_deg, prim_peak = logits_reg_to_deg(out_logits, out_reg)

            if backup_model:
                out_logits_b, out_reg_b = backup_model(xb)
                backup_deg, backup_peak = logits_reg_to_deg(out_logits_b, out_reg_b)
                # gemischtes Score-Maß
                final_score = (primary_weight*prim_peak + backup_weight*backup_peak) / (primary_weight + backup_weight)
                # wähle das Modell mit höherem Score
                final_pred_deg = prim_deg if prim_peak > backup_peak else backup_deg
            else:
                final_score = prim_peak
                final_pred_deg = prim_deg

        if final_score > best_score:
            best_score = final_score
            best = (final_pred_deg, el)

    if best:
        final_az, final_el = best
        dish.move_to(final_az, final_el)
        final_snr = get_real_snr(final_az, final_el, sim_snr)

        if final_snr < 0.8 * sim_snr:
            print("Warning: Low SNR detected. Performing finer scan...")
            rescan_cands = generate_candidates(final_az, final_el, grid_deg=2.0, steps=10)
            best_rescan, best_rescan_score = None, -1.0

            for az, el in rescan_cands:
                feat = normalize(az, el, sim_freq, sim_bw, sim_snr, sim_doppler, sim_pol, sim_pp, sim_sig_type, sim_noise)
                xb = torch.from_numpy(feat).unsqueeze(0).to(DEVICE)

                with torch.no_grad():
                    out_logits, out_reg = model(xb)
                    prim_deg, prim_peak = logits_reg_to_deg(out_logits, out_reg)

                    if backup_model:
                        out_logits_b, out_reg_b = backup_model(xb)
                        backup_deg, backup_peak = logits_reg_to_deg(out_logits_b, out_reg_b)
                        final_score = (primary_weight*prim_peak + backup_weight*backup_peak) / (primary_weight + backup_weight)
                        final_pred_deg = prim_deg if prim_peak > backup_peak else backup_deg
                    else:
                        final_score = prim_peak
                        final_pred_deg = prim_deg

                if final_score > best_rescan_score:
                    best_rescan_score = final_score
                    best_rescan = (final_pred_deg, el)

            if best_rescan:
                final_az, final_el = best_rescan
                dish.move_to(final_az, final_el)
                final_snr = get_real_snr(final_az, final_el, sim_snr)
                print(f"Correction successful. Az: {final_az:.5f}, El: {final_el:.5f}, SNR: {final_snr:.2f}")
        else:
            print(f"Best candidate found. Az: {final_az:.5f}, El: {final_el:.5f}, SNR: {final_snr:.2f}")

# TODO: more accurate positions