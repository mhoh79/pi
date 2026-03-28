/**
 * sensor-stream.js - ES module Node.js sensor streaming server.
 *
 * Simulates TMP102, BME280, BH1750, and MPU6050 readings and exposes them
 * via a lightweight HTTP server on port 8080:
 *
 *   GET /            - HTML dashboard (auto-refreshes via SSE)
 *   GET /api/sensors - JSON snapshot of current readings
 *   GET /api/stream  - Server-Sent Events stream
 *
 * No external dependencies are required for the mock mode; onoff and
 * i2c-bus are listed in package.json as optional for real hardware use.
 */

import http from "http";
import os from "os";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const PORT = Number(process.env.PORT ?? 8080);
const POLL_INTERVAL_MS = Number(process.env.POLL_INTERVAL_MS ?? 1000);

// ---------------------------------------------------------------------------
// Sensor simulation helpers
// ---------------------------------------------------------------------------

/** Slow sinusoidal drift centred on zero. */
function sineDrift(periodSecs = 120, amplitude = 1) {
  const t = Date.now() / 1000;
  return amplitude * Math.sin((2 * Math.PI * t) / periodSecs);
}

/** Gaussian noise via Box-Muller transform. */
function gaussianNoise(sigma = 0.05) {
  const u1 = 1 - Math.random();
  const u2 = 1 - Math.random();
  return sigma * Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

function noisy(base, sigma = 0.05) {
  return base + gaussianNoise(sigma);
}

// ---------------------------------------------------------------------------
// Mock I2C read functions (one per sensor profile)
// ---------------------------------------------------------------------------

function readTMP102() {
  const temp = noisy(22 + sineDrift(120, 3), 0.1);
  return { temperature_c: +temp.toFixed(3) };
}

function readBME280() {
  const temp     = noisy(22   + sineDrift(90,  2),   0.08);
  const humidity = noisy(45   + sineDrift(180, 5),   0.5);
  const pressure = noisy(1013.25 + sineDrift(300, 2), 0.1);
  return {
    temperature_c: +temp.toFixed(3),
    humidity_pct:  +Math.max(0, Math.min(100, humidity)).toFixed(3),
    pressure_hpa:  +pressure.toFixed(3),
  };
}

function readBH1750() {
  const lux = noisy(300 + sineDrift(60, 50), 5);
  return { illuminance_lux: +Math.max(0, lux).toFixed(2) };
}

function readMPU6050() {
  const ax = noisy(sineDrift(45, 0.02), 0.005);
  const ay = noisy(sineDrift(55, 0.02), 0.005);
  const az = noisy(1 + sineDrift(65, 0.01), 0.005);
  return {
    accel_x_g: +ax.toFixed(5),
    accel_y_g: +ay.toFixed(5),
    accel_z_g: +az.toFixed(5),
  };
}

/** Sensor profiles: address -> { name, readFn } */
const SENSORS = [
  { address: 0x48, name: "TMP102",  readFn: readTMP102  },
  { address: 0x76, name: "BME280",  readFn: readBME280  },
  { address: 0x23, name: "BH1750",  readFn: readBH1750  },
  { address: 0x68, name: "MPU6050", readFn: readMPU6050 },
];

// ---------------------------------------------------------------------------
// State: latest readings cache
// ---------------------------------------------------------------------------

let latestReadings = [];

function pollSensors() {
  latestReadings = SENSORS.map(({ address, name, readFn }) => ({
    sensor: name,
    address: `0x${address.toString(16).toUpperCase().padStart(2, "0")}`,
    timestamp: new Date().toISOString(),
    values: readFn(),
  }));
}

// ---------------------------------------------------------------------------
// SSE client registry
// ---------------------------------------------------------------------------

/** @type {Set<import("http").ServerResponse>} */
const sseClients = new Set();

function broadcastSSE(data) {
  const payload = `data: ${JSON.stringify(data)}\n\n`;
  for (const client of sseClients) {
    try {
      client.write(payload);
    } catch {
      sseClients.delete(client);
    }
  }
}

// ---------------------------------------------------------------------------
// HTML dashboard
// ---------------------------------------------------------------------------

function buildDashboard() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RPi Sensor Stream</title>
  <style>
    body { font-family: monospace; background: #0d1117; color: #c9d1d9; margin: 2rem; }
    h1   { color: #58a6ff; }
    .cards { display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 1.5rem; }
    .card {
      background: #161b22; border: 1px solid #30363d; border-radius: 8px;
      padding: 1rem 1.5rem; min-width: 220px;
    }
    .card h2 { margin: 0 0 0.5rem; color: #79c0ff; font-size: 1rem; }
    .card .addr { color: #8b949e; font-size: 0.8rem; margin-bottom: 0.5rem; }
    .val  { color: #a5d6ff; }
    .ts   { color: #484f58; font-size: 0.75rem; margin-top: 0.5rem; }
    #status { color: #3fb950; margin-top: 1rem; font-size: 0.85rem; }
  </style>
</head>
<body>
  <h1>Raspberry Pi Sensor Stream</h1>
  <p style="color:#8b949e">Live data via Server-Sent Events &mdash; updates every ${POLL_INTERVAL_MS} ms</p>
  <div id="status">Connecting&hellip;</div>
  <div class="cards" id="cards"></div>

  <script>
    const cards = document.getElementById("cards");
    const status = document.getElementById("status");
    const cardMap = {};

    function renderCard(reading) {
      let el = cardMap[reading.sensor];
      if (!el) {
        el = document.createElement("div");
        el.className = "card";
        cards.appendChild(el);
        cardMap[reading.sensor] = el;
      }
      const vals = Object.entries(reading.values)
        .map(([k, v]) => \`<div><span style="color:#8b949e">\${k}</span>: <span class="val">\${v}</span></div>\`)
        .join("");
      el.innerHTML = \`
        <h2>\${reading.sensor}</h2>
        <div class="addr">\${reading.address}</div>
        \${vals}
        <div class="ts">\${reading.timestamp}</div>
      \`;
    }

    const evtSource = new EventSource("/api/stream");

    evtSource.onopen = () => {
      status.textContent = "Connected \u2022 receiving live data";
    };

    evtSource.onmessage = (e) => {
      const readings = JSON.parse(e.data);
      readings.forEach(renderCard);
    };

    evtSource.onerror = () => {
      status.textContent = "Connection lost \u2014 retrying\u2026";
      status.style.color = "#f85149";
    };
  </script>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// HTTP request handler
// ---------------------------------------------------------------------------

function handleRequest(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (req.method !== "GET") {
    res.writeHead(405, { "Content-Type": "text/plain" });
    res.end("Method Not Allowed");
    return;
  }

  switch (url.pathname) {
    case "/": {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(buildDashboard());
      break;
    }

    case "/api/sensors": {
      res.writeHead(200, {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
      });
      res.end(JSON.stringify(latestReadings, null, 2));
      break;
    }

    case "/api/stream": {
      res.writeHead(200, {
        "Content-Type":  "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection":    "keep-alive",
        "X-Accel-Buffering": "no",          // disable nginx buffering if proxied
      });
      // Send current readings immediately so the client does not wait.
      res.write(`data: ${JSON.stringify(latestReadings)}\n\n`);
      sseClients.add(res);
      req.on("close", () => sseClients.delete(res));
      break;
    }

    default: {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("Not found");
    }
  }
}

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------

// Seed readings before the server accepts connections.
pollSensors();

const server = http.createServer(handleRequest);

server.listen(PORT, () => {
  const ifaces = os.networkInterfaces();
  const addrs = Object.values(ifaces)
    .flat()
    .filter((i) => i && i.family === "IPv4" && !i.internal)
    .map((i) => `http://${i.address}:${PORT}`);

  console.log(`RPi sensor stream running on port ${PORT}`);
  console.log(`  Dashboard : http://localhost:${PORT}`);
  console.log(`  JSON API  : http://localhost:${PORT}/api/sensors`);
  console.log(`  SSE stream: http://localhost:${PORT}/api/stream`);
  if (addrs.length) {
    console.log(`  Network   : ${addrs.join(", ")}`);
  }
  console.log(`  Poll      : ${POLL_INTERVAL_MS} ms`);
  console.log("Press Ctrl-C to stop.\n");
});

// Poll and broadcast on each tick.
setInterval(() => {
  pollSensors();
  broadcastSSE(latestReadings);
}, POLL_INTERVAL_MS);

// Graceful shutdown.
function shutdown(signal) {
  console.log(`\nReceived ${signal}. Closing server.`);
  server.close(() => process.exit(0));
}

process.on("SIGINT",  () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
