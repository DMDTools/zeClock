#!/usr/bin/env python3
"""Virtual DMD server with browser preview.

Accepts DMDStream protocol on port 6789 (like real dmdserver).
Serves a live DMD preview at http://localhost:8080 via WebSocket.
"""
import asyncio
import base64
import io
import socket
import struct
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

try:
    import websockets
    import websockets.server
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

from PIL import Image

DMD_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6789
WEB_PORT = 8080
WS_PORT = 8081

# Shared state: latest frame as PNG base64
latest_frame_b64 = ""
frame_lock = threading.Lock()
frame_count = 0


def rgb565_to_rgb(data: bytes, width: int, height: int) -> Image.Image:
    """Convert RGB565 big-endian bytes to PIL RGB Image."""
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for i in range(width * height):
        hi = data[i * 2]
        lo = data[i * 2 + 1]
        val = (hi << 8) | lo
        r = ((val >> 11) & 0x1F) << 3
        g = ((val >> 5) & 0x3F) << 2
        b = (val & 0x1F) << 3
        pixels[i % width, i // width] = (r, g, b)
    return img


def rgb24_to_rgb(data: bytes, width: int, height: int) -> Image.Image:
    """Convert RGB24 bytes to PIL RGB Image."""
    return Image.frombytes("RGB", (width, height), data)


def frame_to_b64png(img: Image.Image) -> str:
    """Convert PIL Image to base64-encoded PNG (native resolution)."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>zeClock Virtual DMD</title>
<style>
  body { background: #0a0a0a; margin: 0; display: flex; align-items: center;
         justify-content: center; height: 100vh; flex-direction: column; }
  #dmd-container {
    background: #050505;
    border: 6px solid #1a1a1a;
    border-radius: 10px;
    padding: 8px;
    box-shadow: 0 0 30px rgba(0,0,0,0.9), inset 0 0 15px rgba(0,0,0,0.6);
  }
  canvas { display: block; border-radius: 4px; }
  h1 { color: #f80; font-family: monospace; font-size: 32px; margin-bottom: 18px;
       text-shadow: 0 0 12px rgba(255,136,0,0.5); }
  #fps { color: #aaa; font-family: monospace; font-size: 20px; margin-top: 12px; }
  #rec-btn { margin-top: 14px; padding: 10px 24px; font-family: monospace; font-size: 18px;
    background: #222; color: #ccc; border: 1px solid #444; border-radius: 4px; cursor: pointer; }
  #rec-btn:hover { background: #333; }
  #rec-btn.recording { background: #600; color: #f66; border-color: #f44; }
  #resolution { color: #aaa; font-family: monospace; font-size: 18px; margin-top: 8px; }
  #resolution .mode { color: #f80; font-weight: bold; }
  #hint { color: #666; font-family: monospace; font-size: 15px; margin-top: 16px; max-width: 700px; text-align: center; }
</style>
</head>
<body>
<h1>&#x1f4a1; zeClock Virtual DMD</h1>
<div id="dmd-container">
  <canvas id="dmd" width="1536" height="384"></canvas>
</div>
<div id="fps">Connecting...</div>
<div id="resolution">Resolution: <span class="mode">128x32 (SD)</span></div>
<button id="rec-btn" onclick="toggleRecord()">&#x1F534; Record</button>
<div id="hint">Resolution auto-adapts to zeClock. Use <code>zeclock --hd</code> or <code>make dev-start-virtual-hd</code> for 256x64.</div>
<script>
// DMD dimensions — updated dynamically from first frame
let DMD_W = 128, DMD_H = 32;
let needsReinit = false;
const canvas = document.getElementById("dmd");
const gl = canvas.getContext("webgl2");
if (!gl) { alert("WebGL2 required"); }

// --- Shaders ---

// Full-screen quad vertex shader
const vsQuad = `#version 300 es
in vec2 a_pos;
out vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  v_uv.y = 1.0 - v_uv.y;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;

// Gaussian blur shader (separable, 5-tap)
const fsBlur = `#version 300 es
precision highp float;
in vec2 v_uv;
uniform sampler2D u_tex;
uniform vec2 u_dir; // (1/w, 0) or (0, 1/h)
out vec4 fragColor;
void main() {
  vec2 off1 = 1.3846153846 * u_dir;
  vec2 off2 = 3.2307692308 * u_dir;
  vec3 c = texture(u_tex, v_uv).rgb * 0.2270270270;
  c += texture(u_tex, v_uv + off1).rgb * 0.3162162162;
  c += texture(u_tex, v_uv - off1).rgb * 0.3162162162;
  c += texture(u_tex, v_uv + off2).rgb * 0.0702702703;
  c += texture(u_tex, v_uv - off2).rgb * 0.0702702703;
  fragColor = vec4(c, 1.0);
}`;

// DMD final compositing shader (inspired by Freezy's dmd-extensions)
const fsDmd = `#version 300 es
precision highp float;
in vec2 v_uv;
uniform sampler2D u_dmd;      // base DMD texture
uniform sampler2D u_dotGlow;  // small blur
uniform sampler2D u_backGlow; // large blur
uniform vec2 u_dmdSize;       // 128, 32 or 256, 64
out vec4 fragColor;

// SDF rounded box (from iq)
float udRoundBox(vec2 p, float b, float r) {
  vec2 q = abs(p) - b + r;
  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

void main() {
  // Dot parameters (Freezy-style)
  float dotSize = 0.7;
  float dotRounding = 0.5;
  float dotSharpness = 0.8;
  float sharpMax = 0.01 + dotSize * (1.0 - dotSharpness);
  float sharpMin = -0.01 - dotSize * (1.0 - dotSharpness);

  // Sampling position: (0,0) at dot center, (-1,-1) to (1,1) at corners
  vec2 cellUv = fract(v_uv * u_dmdSize);
  vec2 pos = 2.0 * (cellUv - 0.5);

  // Nearest-neighbor sample of the DMD
  vec2 nearest = (floor(v_uv * u_dmdSize) + 0.5) / u_dmdSize;
  vec3 dmdColor = texture(u_dmd, nearest).rgb;

  // Dot shape via SDF
  float dot = smoothstep(sharpMax, sharpMin, udRoundBox(pos, dotSize, dotRounding * dotSize));

  // Unlit dot (dark gray, always visible)
  vec3 unlitDot = vec3(0.008, 0.008, 0.008);
  vec3 dotColor = (dmdColor + unlitDot) * dot;

  // Dot glow (small blur — nearby lamp bleed)
  vec3 dotGlowColor = texture(u_dotGlow, v_uv).rgb;
  dotColor += dotGlowColor * 0.18;

  // Back glow (large blur — diffuse background light)
  vec3 backGlowColor = texture(u_backGlow, v_uv).rgb;
  dotColor += backGlowColor * 0.06;

  // Brightness
  dotColor *= 1.3;

  // Gamma correction
  dotColor = pow(dotColor, vec3(1.0 / 1.8));

  fragColor = vec4(dotColor, 1.0);
}`;

// --- WebGL helpers ---
function compile(src, type) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
    console.error(gl.getShaderInfoLog(s));
  return s;
}
function link(vs, fs) {
  const p = gl.createProgram();
  gl.attachShader(p, compile(vs, gl.VERTEX_SHADER));
  gl.attachShader(p, compile(fs, gl.FRAGMENT_SHADER));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS))
    console.error(gl.getProgramInfoLog(p));
  return p;
}
function createFBO(w, h) {
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  const fbo = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return { fbo, tex };
}

// --- Setup ---
const blurProg = link(vsQuad, fsBlur);
const dmdProg = link(vsQuad, fsDmd);

// Quad VBO
const quadBuf = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);

// DMD source texture (NEAREST sampling)
let dmdTex = gl.createTexture();
gl.bindTexture(gl.TEXTURE_2D, dmdTex);
gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, DMD_W, DMD_H, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(DMD_W*DMD_H*4));

// FBOs for blur passes (at DMD resolution for efficiency)
let fboBlurH = createFBO(DMD_W, DMD_H);
let fboDotGlow = createFBO(DMD_W, DMD_H);
let fboBlurH2 = createFBO(DMD_W, DMD_H);
let fboBackGlow = createFBO(DMD_W, DMD_H);

// Reinitialize WebGL resources when resolution changes
// Canvas always stays at fixed physical size (same as HD: 1536x384).
// In SD mode, dots are simply larger (12px per dot vs 6px per dot in HD).
const CANVAS_W = 1536;
const CANVAS_H = 384;
function reinitForSize(w, h) {
  DMD_W = w; DMD_H = h;
  // Canvas stays fixed size — dots scale automatically via the shader
  canvas.width = CANVAS_W;
  canvas.height = CANVAS_H;
  // Update resolution indicator
  const dotsPerPx = (CANVAS_W / w).toFixed(0);
  const mode = (w >= 256 && h >= 64) ? "HD" : "SD";
  document.getElementById("resolution").innerHTML =
    'Resolution: <span class="mode">' + w + 'x' + h + ' (' + mode + ', ' + dotsPerPx + 'px/dot)</span>';
  // Recreate DMD texture
  gl.bindTexture(gl.TEXTURE_2D, dmdTex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, DMD_W, DMD_H, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(DMD_W*DMD_H*4));
  // Recreate FBOs at new resolution
  fboBlurH = createFBO(DMD_W, DMD_H);
  fboDotGlow = createFBO(DMD_W, DMD_H);
  fboBlurH2 = createFBO(DMD_W, DMD_H);
  fboBackGlow = createFBO(DMD_W, DMD_H);
  // Update offscreen canvas
  offscreen.width = DMD_W; offscreen.height = DMD_H;
  needsReinit = false;
}

function drawQuad(prog) {
  const loc = gl.getAttribLocation(prog, "a_pos");
  gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
}

function render() {
  // Pass 1: Blur H (dmdTex → fboBlurH)
  gl.bindFramebuffer(gl.FRAMEBUFFER, fboBlurH.fbo);
  gl.viewport(0, 0, DMD_W, DMD_H);
  gl.useProgram(blurProg);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, dmdTex);
  // For blur, use LINEAR sampling on source
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.uniform1i(gl.getUniformLocation(blurProg, "u_tex"), 0);
  gl.uniform2f(gl.getUniformLocation(blurProg, "u_dir"), 1.0/DMD_W, 0.0);
  drawQuad(blurProg);

  // Pass 2: Blur V (fboBlurH → fboDotGlow) = dot glow (small blur)
  gl.bindFramebuffer(gl.FRAMEBUFFER, fboDotGlow.fbo);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, fboBlurH.tex);
  gl.uniform2f(gl.getUniformLocation(blurProg, "u_dir"), 0.0, 1.0/DMD_H);
  drawQuad(blurProg);

  // Pass 3: Blur H again (fboDotGlow → fboBlurH2) for back glow
  gl.bindFramebuffer(gl.FRAMEBUFFER, fboBlurH2.fbo);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, fboDotGlow.tex);
  gl.uniform2f(gl.getUniformLocation(blurProg, "u_dir"), 2.0/DMD_W, 0.0);
  drawQuad(blurProg);

  // Pass 4: Blur V (fboBlurH2 → fboBackGlow) = back glow (large blur)
  gl.bindFramebuffer(gl.FRAMEBUFFER, fboBackGlow.fbo);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, fboBlurH2.tex);
  gl.uniform2f(gl.getUniformLocation(blurProg, "u_dir"), 0.0, 2.0/DMD_H);
  drawQuad(blurProg);

  // Final pass: DMD composite (to screen)
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.useProgram(dmdProg);

  // Restore NEAREST on dmdTex for the dot shader
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, dmdTex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.uniform1i(gl.getUniformLocation(dmdProg, "u_dmd"), 0);

  gl.activeTexture(gl.TEXTURE1);
  gl.bindTexture(gl.TEXTURE_2D, fboDotGlow.tex);
  gl.uniform1i(gl.getUniformLocation(dmdProg, "u_dotGlow"), 1);

  gl.activeTexture(gl.TEXTURE2);
  gl.bindTexture(gl.TEXTURE_2D, fboBackGlow.tex);
  gl.uniform1i(gl.getUniformLocation(dmdProg, "u_backGlow"), 2);

  gl.uniform2f(gl.getUniformLocation(dmdProg, "u_dmdSize"), DMD_W, DMD_H);
  drawQuad(dmdProg);
}

// --- Frame input ---
const frameImg = new Image();
const offscreen = document.createElement("canvas");
offscreen.width = DMD_W; offscreen.height = DMD_H;
const offCtx = offscreen.getContext("2d", {willReadFrequently: true});

let fc = 0, lastT = Date.now();
function connect() {
  const ws = new WebSocket("ws://localhost:WS_PORT/");
  ws.onmessage = (e) => {
    frameImg.onload = () => {
      // Detect resolution change from incoming frame
      if (frameImg.naturalWidth !== DMD_W || frameImg.naturalHeight !== DMD_H) {
        if (frameImg.naturalWidth > 0 && frameImg.naturalHeight > 0) {
          reinitForSize(frameImg.naturalWidth, frameImg.naturalHeight);
        }
      }
      offCtx.drawImage(frameImg, 0, 0, DMD_W, DMD_H);
      const imgData = offCtx.getImageData(0, 0, DMD_W, DMD_H);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, dmdTex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, DMD_W, DMD_H, 0, gl.RGBA, gl.UNSIGNED_BYTE, imgData.data);
      render();
      fc++;
      const now = Date.now();
      if (now - lastT >= 1000) {
        document.getElementById("fps").textContent = fc + " FPS (" + DMD_W + "x" + DMD_H + ")";
        fc = 0; lastT = now;
      }
    };
    frameImg.src = "data:image/png;base64," + e.data;
  };
  ws.onclose = () => {
    document.getElementById("fps").textContent = "Disconnected - reconnecting...";
    setTimeout(connect, 2000);
  };
  ws.onerror = () => { ws.close(); };
  ws.onopen = () => {
    document.getElementById("fps").textContent = "Connected";
  };
}
connect();

// --- Recording via MediaRecorder ---
let mediaRecorder = null;
let recordedChunks = [];

function toggleRecord() {
  const btn = document.getElementById("rec-btn");
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    btn.innerHTML = "&#x1F534; Record";
    btn.classList.remove("recording");
  } else {
    recordedChunks = [];
    const stream = canvas.captureStream(25);
    const mimeTypes = ["video/webm; codecs=vp9", "video/webm; codecs=vp8", "video/webm", "video/mp4"];
    let mimeType = "";
    for (const mt of mimeTypes) { if (MediaRecorder.isTypeSupported(mt)) { mimeType = mt; break; } }
    if (!mimeType) { alert("No supported video codec found"); return; }
    mediaRecorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 4000000 });
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) recordedChunks.push(e.data); };
    mediaRecorder.onstop = () => {
      const blob = new Blob(recordedChunks, { type: mimeType });
      const ext = mimeType.includes("mp4") ? "mp4" : "webm";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "zeclock-demo." + ext;
      a.click();
      URL.revokeObjectURL(url);
    };
    mediaRecorder.start();
    btn.innerHTML = "&#x23F9; Stop";
    btn.classList.add("recording");
  }
}
</script>
</body>
</html>""".replace("WS_PORT", str(WS_PORT))


class WebHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode())

    def log_message(self, format, *args):
        pass  # Silence HTTP logs


def run_web_server():
    """Serve the HTML page."""
    httpd = HTTPServer(("0.0.0.0", WEB_PORT), WebHandler)
    httpd.serve_forever()


ws_clients = set()


async def ws_handler(websocket):
    """WebSocket handler — sends frames to browser."""
    ws_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        ws_clients.discard(websocket)


async def ws_broadcaster():
    """Broadcast latest frame to all WebSocket clients."""
    global latest_frame_b64
    last_sent = ""
    while True:
        await asyncio.sleep(0.04)  # ~25 FPS max
        with frame_lock:
            current = latest_frame_b64
        if current and current != last_sent and ws_clients:
            last_sent = current
            dead = set()
            for ws in ws_clients.copy():
                try:
                    await ws.send(current)
                except Exception:
                    dead.add(ws)
            ws_clients.difference_update(dead)


async def run_ws_server():
    """Run WebSocket server."""
    async with websockets.server.serve(ws_handler, "0.0.0.0", WS_PORT):
        await ws_broadcaster()


def read_exact(conn, n):
    """Read exactly n bytes from socket."""
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def handle_client(conn, addr):
    """Handle a single DMDStream client connection."""
    global latest_frame_b64, frame_count
    print(f"  📡 Client connected: {addr}")
    t0 = time.time()
    local_count = 0

    try:
        while True:
            header = read_exact(conn, 25)
            if header is None:
                break

            magic = header[:10]
            if magic != b"DMDStream\x00":
                print(f"  ⚠️  Bad magic: {magic!r}")
                break

            mode = struct.unpack(">I", header[11:15])[0]
            width = struct.unpack(">H", header[15:17])[0]
            height = struct.unpack(">H", header[17:19])[0]
            length = struct.unpack(">I", header[21:25])[0]

            if length > 0:
                payload = read_exact(conn, length)
                if payload is None:
                    break
            else:
                continue

            # Convert frame to image
            try:
                if mode == 3:  # RGB565
                    img = rgb565_to_rgb(payload, width, height)
                elif mode == 2:  # RGB24
                    img = rgb24_to_rgb(payload, width, height)
                else:
                    continue

                b64 = frame_to_b64png(img)
                with frame_lock:
                    latest_frame_b64 = b64
            except Exception:
                pass

            local_count += 1
            frame_count += 1

            if local_count % 50 == 0:
                elapsed = time.time() - t0
                fps = local_count / elapsed if elapsed > 0 else 0
                print(f"  🖼️  {local_count} frames ({fps:.1f} FPS)    ", end="\r")

    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        elapsed = time.time() - t0
        print(f"\n  📡 Client disconnected ({local_count} frames in {elapsed:.1f}s)")
        conn.close()


def run_dmd_server():
    """TCP server accepting DMDStream protocol."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", DMD_PORT))
    server.listen(2)
    print(f"  TCP: accepting DMDStream on :{DMD_PORT}")

    try:
        while True:
            conn, addr = server.accept()
            # Handle in thread so we don't block
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


def main():
    if not HAS_WEBSOCKETS:
        print("❌ Missing 'websockets' package. Install with:")
        print("   uv pip install websockets")
        sys.exit(1)

    print(f"🎮 Virtual DMD server (browser preview)")
    print(f"  DMD protocol: port {DMD_PORT}")
    print(f"  Browser view: http://localhost:{WEB_PORT}")
    print()

    # Start web server in thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    # Start DMD TCP server in thread
    dmd_thread = threading.Thread(target=run_dmd_server, daemon=True)
    dmd_thread.start()

    # Run WebSocket server in main asyncio loop
    try:
        asyncio.run(run_ws_server())
    except KeyboardInterrupt:
        print("\n🛑 Stopped")


if __name__ == "__main__":
    main()
