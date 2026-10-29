/**
 * La Jefatura Suite — Self-Hosted WhatsApp Multi-Device Bridge for +1 (786) 657-5441
 *
 * Why this exists alongside Meta Cloud API:
 *   - Meta's "Add a new number" (#2388103) rejects any phone number that is currently active
 *     on a smartphone's WhatsApp app (and deleting the WhatsApp account from the phone would
 *     wipe Juan's mobile app and all his existing WhatsApp Group chats).
 *   - This self-hosted Multi-Device Bridge connects as a standard "Linked Device" (identical to
 *     WhatsApp Web on a desktop computer) via an 8-character Pairing Code or QR Code for
 *     +1 (786) 657-5441, forwarding only selected chats/groups to POST http://127.0.0.1:8931/api/whatsapp/webhook.
 */

const fs = require('fs');
const path = require('path');
const http = require('http');
const pino = require('pino');
const QRCode = require('qrcode');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion
} = require('@whiskeysockets/baileys');

const ROOT = path.resolve(__dirname, '..');
const AUTH_DIR = path.join(ROOT, 'data', 'wa_multidevice_auth');
const STATE_FILE = path.join(ROOT, 'data', 'wa_multidevice_state.json');
const TARGET_PHONE = (process.env.JUAN_WA_PHONE || '17866575441').replace(/\D/g, '');
const MC_PORT = parseInt(process.env.MC_PORT || '8931', 10);

fs.mkdirSync(AUTH_DIR, { recursive: true });

let bridgeState = {
  ok: true,
  mode: 'WhatsApp Multi-Device Linked Companion + Meta Cloud API',
  target_phone: '+1 (786) 657-5441',
  target_phone_digits: TARGET_PHONE,
  connection: 'connecting',
  pairing_code: null,
  qr_data_url: null,
  connected_user: null,
  groups_discovered: [],
  updated_at: new Date().toISOString()
};

function saveState(patch = {}) {
  bridgeState = { ...bridgeState, ...patch, updated_at: new Date().toISOString() };
  try {
    fs.writeFileSync(STATE_FILE, JSON.stringify(bridgeState, null, 2), 'utf8');
  } catch (e) {}
}

function forwardToMissionControl(payload) {
  const data = Buffer.from(JSON.stringify(payload), 'utf8');
  const req = http.request({
    hostname: '127.0.0.1',
    port: MC_PORT,
    path: '/api/whatsapp/webhook',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': data.length
    }
  }, (res) => { res.resume(); });
  req.on('error', () => {});
  req.write(data);
  req.end();
}

let pairingRequested = false;

async function startBridge() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  let version = [2, 3000, 1015901307];
  try {
    const v = await fetchLatestBaileysVersion();
    if (v && v.version) version = v.version;
  } catch (e) {}

  const sock = makeWASocket({
    version,
    logger: pino({ level: 'silent' }),
    printQRInTerminal: false,
    auth: state,
    browser: ['Ubuntu', 'Chrome', '20.0.04']
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      try {
        const qrUrl = await QRCode.toDataURL(qr, { margin: 1, width: 280 });
        saveState({ connection: 'awaiting_scan_or_code', qr_data_url: qrUrl });
      } catch (e) {}

      if (!sock.authState.creds.registered && !pairingRequested && TARGET_PHONE) {
        pairingRequested = true;
        setTimeout(async () => {
          try {
            const code = await sock.requestPairingCode(TARGET_PHONE);
            const formatted = code && code.length === 8 ? `${code.slice(0, 4)}-${code.slice(4)}` : code;
            console.log(`PAIRING_CODE_FOR_${TARGET_PHONE}: ${formatted}`);
            saveState({ pairing_code: formatted, connection: 'awaiting_pairing_code' });
          } catch (err) {
            console.error('Pairing code error:', err.message);
          }
        }, 2000);
      }
    }

    if (connection === 'open') {
      pairingRequested = false;
      saveState({
        connection: 'connected',
        pairing_code: null,
        qr_data_url: null,
        connected_user: sock.user || { id: TARGET_PHONE }
      });
      console.log('CONNECTED_TO_WHATSAPP:', JSON.stringify(sock.user));
      try {
        const groups = await sock.groupFetchAllParticipating();
        const groupList = Object.values(groups).map(g => ({
          chat_id: g.id,
          name: g.subject,
          participants_count: (g.participants || []).length
        }));
        saveState({ groups_discovered: groupList.slice(0, 50) });
      } catch (e) {}
    }

    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = code !== DisconnectReason.loggedOut;
      saveState({ connection: shouldReconnect ? 'reconnecting' : 'logged_out' });
      if (shouldReconnect) {
        pairingRequested = false;
        setTimeout(startBridge, 4000);
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;
    for (const m of messages) {
      if (!m.message || m.key.fromMe) continue;
      const chatId = m.key.remoteJid || '';
      const isGroup = chatId.endsWith('@g.us');
      const text =
        m.message.conversation ||
        m.message.extendedTextMessage?.text ||
        m.message.imageMessage?.caption ||
        '';
      if (!text.trim()) continue;
      const sender = m.pushName || m.key.participant || chatId;
      forwardToMissionControl({
        chat_id: chatId,
        sender: isGroup ? `${sender} (${chatId})` : `${sender} (${chatId.replace('@s.whatsapp.net', '')})`,
        text: text.trim(),
        kind: isGroup ? 'group' : 'direct',
        company: 'building'
      });
    }
  });
}

startBridge().catch((e) => {
  saveState({ connection: 'error', error: e.message });
});
