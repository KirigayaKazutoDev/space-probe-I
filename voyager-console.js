(() => {
  const state = {
    storage: 0,
    locked: false,
    scanner: true,
    buffer: null,
    queue: 0,
    packages: [],
    azimuth: 300.0,
    snr: 10.82,
    link: 98.4
  };

  const $ = (id) => document.getElementById(id);
  const logWindow = $('log-window');

  function addLog(system, message, type = '') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.innerHTML = `<time>${new Date().toLocaleTimeString('de-DE')}</time><strong>[${system}]</strong>${message}`;
    logWindow.appendChild(entry);
    logWindow.scrollTop = logWindow.scrollHeight;
  }

  function updateDisplay() {
    $('clock').textContent = new Date().toLocaleTimeString('de-DE', { hour12: false });
    $('azimuth').textContent = `${state.azimuth.toFixed(4)}°`;
    $('pointing-az').textContent = `${state.azimuth.toFixed(4)}°`;
    $('track-error').textContent = `${Math.abs(state.azimuth - 300).toFixed(4)}°`;
    $('link-quality').textContent = state.link.toFixed(1);
    $('link-meter').style.width = `${state.link}%`;
    $('snr').textContent = state.snr.toFixed(2);
    $('storage-used').textContent = state.storage.toFixed(1);
    $('storage-meter').style.width = `${Math.min(100, state.storage / 50 * 100)}%`;
    $('queue-count').textContent = state.queue;
    $('buffer-state').textContent = state.buffer ? `PKT-${state.buffer.id}` : 'EMPTY';
    $('storage-state').textContent = state.locked ? 'SLOT LOCKED' : 'SLOT OPEN';
    $('payload-chip').textContent = state.locked ? 'AWAITING ACK' : 'READY';
    $('scanner-state').textContent = state.scanner ? 'ACTIVE' : 'STANDBY';
    $('scanner-state').classList.toggle('active', state.scanner);
  }

  function captureObservation() {
    if (!state.scanner) return;
    state.snr = 9.5 + Math.random() * 5.5;
    if (state.snr < 11.4) {
      $('scan-message').textContent = 'SNR unter Schwellwert. Sensor-Array scannt weiter.';
      return;
    }
    if (state.storage + (state.locked ? 0.2 : 4.5) > 50) {
      addLog('STORAGE', 'CRITICAL: Speicherlimit erreicht.', 'warning');
      $('scan-message').textContent = 'Speicherlimit erreicht. Aufnahme ausgesetzt.';
      return;
    }
    const size = state.locked ? 0.2 : 4.5;
    const packet = { id: Math.floor(1000 + Math.random() * 8999), type: state.locked ? 'LR_DATA' : '4K_VIDEO', size };
    state.storage += size;
    if (state.locked) {
      state.queue += 1;
      addLog('STORAGE', `Low-Res Backup erstellt (${size.toFixed(1)} GB).`, 'warning');
      $('scan-message').textContent = `Muster erkannt bei SNR ${state.snr.toFixed(2)} dB. Low-Res Backup eingereiht.`;
    } else {
      state.locked = true;
      state.buffer = packet;
      addLog('AI-SCAN', `Muster erkannt bei SNR ${state.snr.toFixed(2)} dB. Starte KI-Analyse.`, 'success');
      addLog('COMMS', `Downlink aktiv: Sende 4K_VIDEO / PKT-${packet.id}.`);
      $('scan-message').textContent = `4K-Paket PKT-${packet.id} gesichert. Bestätigung der Bodenstation erforderlich.`;
      setTimeout(() => {
        state.packages.unshift({ ...packet, time: new Date().toLocaleTimeString('de-DE') });
        renderPackages();
        addLog('COMMS', `Empfang bestätigt: PKT-${packet.id} liegt auf der Erde vor.`, 'success');
      }, 2200);
    }
    updateDisplay();
  }

  function sendCommand(command) {
    addLog('EARTH', `Uplink command: ${command.toUpperCase()}`);
    setTimeout(() => {
      if (command === 'ack_delete') {
        if (!state.buffer) {
          addLog('CORE', 'ACK abgewiesen: Kein High-Res-Puffer vorhanden.', 'warning');
          return;
        }
        state.storage = Math.max(0, state.storage - state.buffer.size);
        state.buffer = null;
        state.locked = false;
        addLog('CORE', 'ACK authentifiziert. 4.5 GB freigegeben; Slot offen.', 'success');
      } else if (command === 'scan_toggle') {
        state.scanner = !state.scanner;
        addLog('AI-SCAN', `DishNet Scanner ${state.scanner ? 'aktiviert' : 'deaktiviert'}.`, state.scanner ? 'success' : 'warning');
      }
      updateDisplay();
    }, 850);
  }

  function renderPackages() {
    const list = $('package-list');
    list.innerHTML = state.packages.length ? state.packages.map((packet) => `<div class="package"><strong>${packet.type} / PKT-${packet.id}</strong><span>${packet.size.toFixed(1)} GB · ${packet.time}</span></div>`).join('') : '<div class="empty-state">NO PACKAGES RECEIVED THIS SESSION</div>';
  }

  document.querySelectorAll('[data-view]').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.screen-view').forEach((view) => view.classList.remove('active-view'));
      $(button.dataset.view).classList.add('active-view');
    });
  });
  document.querySelectorAll('[data-command]').forEach((button) => button.addEventListener('click', () => sendCommand(button.dataset.command)));
  $('clear-log').addEventListener('click', () => { logWindow.innerHTML = ''; addLog('CORE', 'Lokales Ereignisprotokoll gelöscht.'); });

  addLog('CORE', 'Voyager 3 Core online. Antimaterie-Reaktor stabil.', 'success');
  addLog('POINTING', 'Autonome Ausrichtung gestartet. Ziel: Erde / DSN.');
  addLog('COMMS', 'Radio-Empfänger aktiv. Suche Trägerwelle auf Erdfrequenz.');
  updateDisplay();
  setInterval(() => {
    state.azimuth = 300 + (Math.random() - 0.5) * 0.08;
    state.link = 96 + Math.random() * 3.8;
    updateDisplay();
  }, 1800);
  setInterval(captureObservation, 7000);
})();
