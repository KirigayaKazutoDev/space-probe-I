import React, { useState, useEffect, useRef } from 'react';
import { 
  Terminal as TerminalIcon, 
  Satellite, 
  Zap, 
  Database, 
  ShieldCheck, 
  Video, 
  Camera, 
  Cpu,
  Send,
  Trash2,
  AlertTriangle,
  Activity
} from 'lucide-react';

// --- KONSTANTEN ---
const MAX_STORAGE_GB = 50;
const SIGNAL_DELAY_MS = 5000; 

const App = () => {
  // --- STATE MISSION CONTROL (ERDE) ---
  const [earthTerminal, setEarthTerminal] = useState([{ msg: "System bereit. Warte auf Telemetrie...", type: "system", time: new Date().toLocaleTimeString() }]);
  const [commandInput, setCommandInput] = useState("");
  const [receivedData, setReceivedData] = useState([]);
  
  // Ref für Auto-Scroll
  const terminalEndRef = useRef(null);
  
  // --- STATE VOYAGER 3 (SONDE) ---
  const [storageUsed, setStorageUsed] = useState(0);
  const [isWaitingForAck, setIsWaitingForAck] = useState(false);
  const [currentBuffer, setCurrentBuffer] = useState(null); 
  const [tempQueue, setTempQueue] = useState([]); 
  const [reaktorStatus, setReaktorStatus] = useState("Stabil");
  const [isTransmitting, setIsTransmitting] = useState(false);
  const [aiScannerActive, setAiScannerActive] = useState(true);

  // Auto-Scroll Funktion
  const scrollToBottom = () => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [earthTerminal]);

  // Simuliere die KI-Erkennung & Video-Aufnahme
  useEffect(() => {
    const interval = setInterval(() => {
      if (!isWaitingForAck && aiScannerActive) {
        captureHighResData();
      } else if (isWaitingForAck) {
        captureLowResData();
      }
    }, 8000);
    return () => clearInterval(interval);
  }, [isWaitingForAck, aiScannerActive, storageUsed]);

  const captureHighResData = () => {
    const size = 4.5;
    if (storageUsed + size <= MAX_STORAGE_GB) {
      const newVideo = { id: Date.now(), type: '4K_VIDEO', size, quality: 'Ultra HD', timestamp: new Date().toLocaleTimeString() };
      setCurrentBuffer(newVideo);
      setStorageUsed(prev => prev + size);
      startTransmission(newVideo);
    }
  };

  const captureLowResData = () => {
    const size = 0.2;
    if (storageUsed + size <= MAX_STORAGE_GB) {
      const lowRes = { id: Date.now(), type: 'LR_VIDEO', size, quality: 'Low Res', timestamp: new Date().toLocaleTimeString() };
      setTempQueue(prev => [...prev, lowRes]);
      setStorageUsed(prev => prev + size);
    }
  };

  const startTransmission = (data) => {
    setIsTransmitting(true);
    setIsWaitingForAck(true);
    
    setTimeout(() => {
      receiveOnEarth(data);
      setIsTransmitting(false);
    }, SIGNAL_DELAY_MS);
  };

  const receiveOnEarth = (data) => {
    const msg = `Empfange Daten: ${data.type} (${data.quality}) - Größe: ${data.size} GB`;
    addEarthLog(msg, "success");
    setReceivedData(prev => [data, ...prev]);
  };

  const addEarthLog = (msg, type = "info") => {
    // Neue Nachrichten kommen UNTEN hinzu für echtes Terminal-Feeling
    setEarthTerminal(prev => [...prev, { msg, type, time: new Date().toLocaleTimeString() }]);
  };

  const handleCommand = (e) => {
    e.preventDefault();
    if (!commandInput) return;

    const cmd = commandInput.toLowerCase();
    addEarthLog(`> SENDING COMMAND: ${cmd}`, "command");

    setTimeout(() => {
      processCommandAtSonde(cmd);
    }, SIGNAL_DELAY_MS);

    setCommandInput("");
  };

  const processCommandAtSonde = (cmd) => {
    if (cmd === "ack_delete" || cmd === "1") {
      if (currentBuffer) {
        const freed = currentBuffer.size;
        setStorageUsed(prev => Math.max(0, prev - freed));
        setCurrentBuffer(null);
        setIsWaitingForAck(false);
        addEarthLog("CONFIRMED: Sonde hat Puffer gelöscht. Neuer Slot frei.", "system");
        
        if (tempQueue.length > 0) {
           addEarthLog("Sonde beginnt mit Nachsenden der Low-Res Queue...", "info");
        }
      }
    } else if (cmd === "scan_off") {
      setAiScannerActive(false);
      addEarthLog("Sonde: KI-Scanner deaktiviert.", "warning");
    } else if (cmd === "scan_on") {
      setAiScannerActive(true);
      addEarthLog("Sonde: KI-Scanner aktiviert.", "system");
    } else {
      addEarthLog("FEHLER: Unbekannter Geheimcode oder Befehl.", "error");
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-4 font-mono flex flex-col md:flex-row gap-4 max-h-screen overflow-hidden">
      
      {/* --- MISSION CONTROL (ERDE) --- */}
      <div className="flex-1 flex flex-col gap-4 border border-slate-800 rounded-xl p-4 bg-slate-900/50 backdrop-blur-md overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Satellite className="text-blue-400" /> MISSION CONTROL
          </h2>
          <div className="flex gap-2 items-center">
             <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
             <span className="text-[10px] text-slate-500 uppercase tracking-widest">Link Active</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700">
            <span className="text-[10px] text-slate-400 block mb-1 uppercase tracking-tighter">Empfangene Dateien</span>
            <div className="text-2xl font-bold">{receivedData.length}</div>
          </div>
          <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700">
            <span className="text-[10px] text-slate-400 block mb-1 uppercase tracking-tighter">Signal-Verzögerung</span>
            <div className="text-2xl font-bold">5.0s <span className="text-xs text-slate-500">sim</span></div>
          </div>
        </div>

        {/* TERMINAL MIT FIXED HEIGHT UND SCROLL */}
        <div className="flex-1 bg-black rounded-lg p-4 overflow-y-auto border border-slate-800 text-sm shadow-inner custom-scrollbar relative">
          <div className="absolute top-2 right-4 text-[10px] text-slate-700 pointer-events-none">TTY/DSN-01</div>
          {earthTerminal.map((log, i) => (
            <div key={i} className={`mb-1 break-words ${
              log.type === "error" ? "text-red-500" : 
              log.type === "success" ? "text-emerald-400" : 
              log.type === "command" ? "text-amber-400" : 
              log.type === "system" ? "text-blue-400 font-bold" : "text-slate-300"
            }`}>
              <span className="text-slate-600 mr-2 font-light">[{log.time}]</span>
              <span className="opacity-90">{log.msg}</span>
            </div>
          ))}
          {/* Dummy Element für Auto-Scroll */}
          <div ref={terminalEndRef} />
        </div>

        <form onSubmit={handleCommand} className="flex gap-2">
          <div className="flex-1 relative">
            <span className="absolute left-3 top-2.5 text-blue-500 text-xs">$</span>
            <input 
              className="w-full bg-slate-800 border border-slate-700 rounded pl-7 pr-3 py-2 text-sm outline-none focus:border-blue-500 transition-colors"
              placeholder="Command..."
              value={commandInput}
              onChange={(e) => setCommandInput(e.target.value)}
            />
          </div>
          <button className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded flex items-center gap-2 transition-all font-bold text-xs">
            <Send size={14} /> SEND
          </button>
        </form>

        <div className="flex gap-2">
          {['ACK_DELETE', 'SCAN_ON', 'SCAN_OFF'].map(cmd => (
            <button 
              key={cmd}
              onClick={() => setCommandInput(cmd.toLowerCase())} 
              className="text-[10px] bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded text-slate-400 transition-colors"
            >
              {cmd}
            </button>
          ))}
        </div>
      </div>

      {/* --- VOYAGER 3 CORE STATUS --- */}
      <div className="w-full md:w-96 flex flex-col gap-4 border border-blue-900/30 rounded-xl p-4 bg-slate-900/80 shadow-2xl overflow-y-auto">
        <div className="flex items-center gap-2 border-b border-blue-900/30 pb-2">
          <Cpu className="text-purple-400" size={20} />
          <h2 className="font-bold text-lg uppercase tracking-wider">Voyager 3 Core</h2>
        </div>

        <div className="space-y-4">
          <div className="bg-slate-950/40 p-3 rounded-lg border border-slate-800">
            <div className="flex justify-between items-center text-[10px] mb-2 uppercase text-slate-500 tracking-widest">
              <span className="flex items-center gap-1"><Zap size={12} className="text-yellow-400" /> Energie-System</span>
              <span className="text-blue-400">{reaktorStatus}</span>
            </div>
            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
               <div className="h-full bg-blue-500 animate-pulse" style={{ width: '100%' }} />
            </div>
          </div>

          <div className="bg-slate-950/40 p-3 rounded-lg border border-slate-800">
            <div className="flex justify-between mb-2 items-end">
              <span className="text-[10px] flex items-center gap-1 uppercase text-slate-500 tracking-widest"><Database size={12} /> Storage (MRAM)</span>
              <span className={`text-xs font-bold ${storageUsed > 40 ? 'text-red-400' : 'text-blue-400'}`}>
                {storageUsed.toFixed(1)} / {MAX_STORAGE_GB} GB
              </span>
            </div>
            <div className="w-full h-3 bg-slate-800 rounded-sm border border-slate-700 overflow-hidden p-0.5">
              <div 
                className={`h-full transition-all duration-700 rounded-sm ${storageUsed > 40 ? 'bg-red-500' : 'bg-blue-500'}`} 
                style={{ width: `${(storageUsed / MAX_STORAGE_GB) * 100}%` }} 
              />
            </div>
            <div className="mt-2 flex justify-between text-[9px] text-slate-600 uppercase">
              <span>Slot: {isWaitingForAck ? 'Locked' : 'Open'}</span>
              <span>Temp: {tempQueue.length} Files</span>
            </div>
          </div>

          <div className="bg-slate-950/40 p-3 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-500 mb-3 flex items-center gap-1 uppercase tracking-widest">
              <Activity size={12} /> Core Operations
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">AI Scanner</span>
                <span className={`text-[10px] px-2 py-0.5 rounded ${aiScannerActive ? 'bg-purple-900/30 text-purple-400 border border-purple-800' : 'bg-slate-800 text-slate-600'}`}>
                  {aiScannerActive ? 'ACTIVE' : 'STANDBY'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">Uplink Status</span>
                <span className={`text-[10px] px-2 py-0.5 rounded ${isTransmitting ? 'bg-yellow-900/30 text-yellow-400 border border-yellow-800 animate-pulse' : 'bg-slate-800 text-slate-500'}`}>
                  {isTransmitting ? 'SENDING' : 'IDLE'}
                </span>
              </div>
            </div>
          </div>

          {isWaitingForAck && (
            <div className="p-3 bg-amber-900/10 border border-amber-900/30 rounded-lg animate-in fade-in slide-in-from-bottom-2">
              <div className="flex items-center gap-2 text-amber-500 text-xs font-bold uppercase mb-1">
                <ShieldCheck size={14} /> Awaiting ACK
              </div>
              <p className="text-[10px] text-amber-200/60 leading-relaxed">
                High-Res Datenpaket im Puffer gesperrt. Bestätigung der Bodenstation erforderlich (Code 1 / ACK_DELETE).
              </p>
            </div>
          )}
        </div>
      </div>

      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: #020617;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #1e293b;
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #334155;
        }
      `}</style>
    </div>
  );
};

export default App;
