import { spawn } from "node:child_process";

const port = Number(process.env.SMOKE_PORT ?? 4173);
const baseUrl = `http://127.0.0.1:${port}`;
const paths = ["/", "/approvals", "/reports"];
const shellMarker = '<div id="root"></div>';
const startupTimeoutMs = 10_000;

if (!Number.isInteger(port) || port < 1 || port > 65_535) {
  throw new Error(`SMOKE_PORT must be an integer between 1 and 65535; received ${port}`);
}

const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const preview = spawn(
  npmCommand,
  ["run", "preview", "--", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
  {
    cwd: new URL("..", import.meta.url),
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
  },
);

let previewOutput = "";
preview.stdout.on("data", (chunk) => {
  previewOutput += chunk.toString();
});
preview.stderr.on("data", (chunk) => {
  previewOutput += chunk.toString();
});

function sleep(delayMs) {
  return new Promise((resolve) => setTimeout(resolve, delayMs));
}

async function waitForPreview() {
  const deadline = Date.now() + startupTimeoutMs;
  while (Date.now() < deadline) {
    if (preview.exitCode !== null) {
      throw new Error(`Static preview exited before startup.\n${previewOutput}`);
    }

    try {
      const response = await fetch(`${baseUrl}/`);
      if (response.ok) return;
    } catch {
      // The preview server is still starting.
    }
    await sleep(100);
  }

  throw new Error(`Static preview did not start within ${startupTimeoutMs}ms.\n${previewOutput}`);
}

async function checkPath(path) {
  const response = await fetch(`${baseUrl}${path}`);
  const body = await response.text();
  const contentType = response.headers.get("content-type") ?? "";

  if (response.status !== 200) {
    throw new Error(`${path} returned HTTP ${response.status}, expected 200`);
  }
  if (!contentType.includes("text/html")) {
    throw new Error(`${path} returned ${contentType || "no content type"}, expected HTML`);
  }
  if (!body.includes(shellMarker)) {
    throw new Error(`${path} did not return the SPA shell`);
  }
}

async function stopPreview() {
  if (preview.exitCode !== null) return;

  const terminate = () => {
    if (preview.pid === undefined) return;
    if (process.platform === "win32") {
      preview.kill("SIGTERM");
      return;
    }
    try {
      process.kill(-preview.pid, "SIGTERM");
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
  };

  await new Promise((resolve) => {
    const forceExit = setTimeout(() => {
      if (preview.exitCode === null) preview.kill("SIGKILL");
      resolve();
    }, 1_000);
    preview.once("exit", () => {
      clearTimeout(forceExit);
      resolve();
    });
    terminate();
  });
}

try {
  await waitForPreview();
  for (const path of paths) {
    await checkPath(path);
    console.log(`Static deployment smoke check passed: ${path}`);
  }
} finally {
  await stopPreview();
}