/**
 * Autonomous SRE Agent: Self-Healing DevOps System
 * Target Application
 * ---------------------------------
 * Built by Vignesh Yadala
 * https://vigneshyadala.github.io/portfolio | https://github.com/Vigneshyadala
 * ---------------------------------
 * A small Express API that behaves normally under /health and /data,
 * but exposes intentional "chaos" endpoints used to simulate real
 * production incidents so the SRE-Agent has something real to detect,
 * diagnose, and heal.
 *
 *   GET /health      -> liveness/readiness probe used by the monitor
 *   GET /data        -> normal "business" endpoint, returns JSON payload
 *   GET /chaos/leak  -> simulates a memory leak (heap grows until OOM/stall)
 *   GET /chaos/db    -> simulates a DB connection failure (persistent 500s)
 *   GET /chaos/cpu   -> simulates a CPU spike (event loop blocked)
 *   POST /chaos/reset-> resets all chaos flags back to healthy state
 */

const express = require('express');
const app = express();
const PORT = process.env.PORT || 3000;

// ---------------------------------------------------------------------------
// In-memory "incident" state. This is what the chaos endpoints flip and what
// the normal endpoints check before responding. It intentionally lives only
// in process memory so that a `docker restart` performed by the SRE-Agent is
// a genuine, effective remediation (the flags reset to a clean state).
// ---------------------------------------------------------------------------
const state = {
  dbConnectionDown: false,
  leakIntervalHandle: null,
  leakedMemoryChunks: [], // holds references so V8 cannot GC them away
  cpuSpikeActive: false,
};

app.use(express.json());

// Basic request logging so Docker logs have real content for the monitor
// and agent to read (mimics a production access log).
app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    const ms = Date.now() - start;
    console.log(
      `[${new Date().toISOString()}] ${req.method} ${req.originalUrl} -> ${res.statusCode} (${ms}ms)`
    );
  });
  next();
});

// ---------------------------------------------------------------------------
// Health endpoint
// ---------------------------------------------------------------------------
app.get('/health', (req, res) => {
  const memUsage = process.memoryUsage();
  const heapUsedMB = Math.round(memUsage.heapUsed / 1024 / 1024);
  const heapTotalMB = Math.round(memUsage.heapTotal / 1024 / 1024);
  const externalMB = Math.round(memUsage.external / 1024 / 1024);
  const rssMB = Math.round(memUsage.rss / 1024 / 1024);

  // Use rss (total process memory), not heapUsed — the leak allocates
  // Buffers which live outside the V8 heap, so heapUsed stays low even
  // while the process genuinely balloons in memory.
  const degraded = state.dbConnectionDown || rssMB > 400;

  if (degraded) {
    return res.status(503).json({
      status: 'DEGRADED',
      reason: state.dbConnectionDown
        ? 'database_connection_refused'
        : 'high_memory_usage',
      heapUsedMB,
      heapTotalMB,
      externalMB,
      rssMB,
      timestamp: new Date().toISOString(),
    });
  }

  return res.status(200).json({
    status: 'OK',
    heapUsedMB,
    heapTotalMB,
    externalMB,
    rssMB,
    uptimeSeconds: Math.round(process.uptime()),
    timestamp: new Date().toISOString(),
  });
});

// ---------------------------------------------------------------------------
// Normal data endpoint
// ---------------------------------------------------------------------------
app.get('/data', (req, res) => {
  if (state.dbConnectionDown) {
    console.error(
      'ERROR: DatabaseConnectionError: connect ECONNREFUSED 127.0.0.1:5432 - database connection refused'
    );
    return res.status(500).json({
      error: 'Database Connection Refused',
      code: 'ECONNREFUSED',
      message: 'connect ECONNREFUSED 127.0.0.1:5432 - could not reach postgres backend',
      timestamp: new Date().toISOString(),
    });
  }

  return res.status(200).json({
    data: [
      { id: 1, name: 'widget-alpha', stock: 42 },
      { id: 2, name: 'widget-beta', stock: 17 },
      { id: 3, name: 'widget-gamma', stock: 8 },
    ],
    timestamp: new Date().toISOString(),
  });
});

// ---------------------------------------------------------------------------
// CHAOS: Memory leak
// Repeatedly allocates 5MB buffers and keeps a reference to every one of
// them so the garbage collector can never reclaim them. Eventually the
// event loop starts stalling under GC pressure and /health starts timing
// out or returning 503/504, which is exactly what the monitor should catch.
// ---------------------------------------------------------------------------
app.get('/chaos/leak', (req, res) => {
  if (state.leakIntervalHandle) {
    return res.status(200).json({
      message: 'Memory leak simulation already running',
      chunksAllocated: state.leakedMemoryChunks.length,
    });
  }

  console.error('WARN: Chaos endpoint triggered -> memory leak simulation starting');

  state.leakIntervalHandle = setInterval(() => {
    // Allocate a 5MB buffer filled with pseudo-random bytes so V8 cannot
    // optimize it away, then hold the reference forever.
    const chunk = Buffer.alloc(5 * 1024 * 1024, Math.floor(Math.random() * 255));
    state.leakedMemoryChunks.push(chunk);

    const rssMB = Math.round(process.memoryUsage().rss / 1024 / 1024);
    console.log(
      `LEAK: allocated chunk #${state.leakedMemoryChunks.length}, rss=${rssMB}MB`
    );

    // Once we're clearly in danger territory, log a heap-out-of-memory style
    // message so the log pattern matches what the RAG runbook expects.
    if (rssMB > 350) {
      console.error(
        'FATAL ERROR: JavaScript heap out of memory - Reached heap limit, process may abort'
      );
    }
  }, 200);

  return res.status(200).json({
    message: 'Memory leak simulation started. Heap will grow ~25MB/sec.',
    warning: 'The process will become unresponsive within seconds.',
  });
});

// ---------------------------------------------------------------------------
// CHAOS: Database corruption / connection failure
// Flips a flag so every subsequent /data call throws a 500 until the flag
// is cleared (either by /chaos/reset or by a container restart).
// ---------------------------------------------------------------------------
app.get('/chaos/db', (req, res) => {
  state.dbConnectionDown = true;
  console.error(
    'ERROR: DatabaseConnectionError: connection to postgres pool lost - all queries will fail until reconnect'
  );
  return res.status(200).json({
    message: 'Database connection chaos injected. /data will now return 500 errors.',
  });
});

// ---------------------------------------------------------------------------
// CHAOS: CPU spike
// Runs a synchronous, CPU-bound loop that blocks the event loop for several
// seconds, causing every other request (including /health) to time out.
// ---------------------------------------------------------------------------
app.get('/chaos/cpu', (req, res) => {
  console.error('WARN: Chaos endpoint triggered -> CPU spike simulation starting');
  state.cpuSpikeActive = true;

  const durationMs = 8000;
  const end = Date.now() + durationMs;

  // Busy-loop: intentionally blocking, single-threaded Node.js event loop
  // starvation to simulate a runaway computation / infinite loop bug.
  let x = 0;
  while (Date.now() < end) {
    x += Math.sqrt(x + 1);
  }

  state.cpuSpikeActive = false;
  return res.status(200).json({
    message: `CPU spike simulation completed after ${durationMs}ms`,
    result: x,
  });
});

// ---------------------------------------------------------------------------
// Remediation helper endpoint: allows the SRE-Agent (or a human) to clear
// chaos flags without necessarily restarting the container. A real
// `docker restart` will also fully reset this state since it's in-memory.
// ---------------------------------------------------------------------------
app.post('/chaos/reset', (req, res) => {
  state.dbConnectionDown = false;
  state.cpuSpikeActive = false;

  if (state.leakIntervalHandle) {
    clearInterval(state.leakIntervalHandle);
    state.leakIntervalHandle = null;
  }
  state.leakedMemoryChunks = [];

  if (global.gc) {
    global.gc(); // only available if node was started with --expose-gc
  }

  console.log('INFO: Chaos state reset to healthy baseline');
  return res.status(200).json({ message: 'All chaos flags reset. System healthy.' });
});

app.listen(PORT, () => {
  console.log(`Target app listening on port ${PORT}`);
});

module.exports = app;