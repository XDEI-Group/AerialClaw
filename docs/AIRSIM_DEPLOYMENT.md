# AirSim Remote Deployment Guide

A complete guide for deploying AerialClaw v2.0 against a remote AirSim server, including all pitfalls encountered and their solutions.

---

## Architecture Overview

```
Local Machine                    Remote Server (GPU)
─────────────────                ──────────────────────────────
AerialClaw server.py             AirSim (UE4 / SimpleFlight)
  └── airsim_adapter.py          port 41451 (localhost only)
      └── airsim_rpc.py
          └── TCP socket
              │
              └──── SSH Tunnel ──────────────────────────────┘
                    localhost:41451 → server:41451
```

---

## 1. Server Setup (Remote)

### 1.1 Available AirSim Environments

The server at `glados@<IP>:37641` has multiple pre-built environments:

```
~/code/openfly/envs/airsim/
├── env_airsim_16/   ← Indoor (AirVLN scene 16)
├── env_airsim_18/
├── env_airsim_23/
├── env_airsim_26/
├── env_airsim_gz/   ← Outdoor (Gazebo-style)
└── env_airsim_sh/   ← Shanghai outdoor scene
```

### 1.2 Starting AirSim (Headless Mode)

AirSim runs headless with `-nullrhi` (no GPU rendering required):

```bash
# Step 1: Make executable (first time only)
chmod +x ~/code/openfly/envs/airsim/env_airsim_16/LinuxNoEditor/start.sh
chmod +x ~/code/openfly/envs/airsim/env_airsim_16/LinuxNoEditor/AirVLN/Binaries/Linux/AirVLN-Linux-Shipping

# Step 2: Start headless
nohup ~/code/openfly/envs/airsim/env_airsim_16/LinuxNoEditor/start.sh \
    -nullrhi > /tmp/airsim.log 2>&1 &

# Step 3: Wait ~20s then verify
ss -tlnp | grep 41451   # should show LISTEN on 0.0.0.0:41451
```

> **Note:** UE4 takes 15-25s to initialize. Check `/tmp/airsim.log` for startup progress.

### 1.3 Server AirSim Settings

Located at `~/Documents/AirSim/settings.json`:
```json
{
  "SettingsVersion": 1.2,
  "SimMode": "Multirotor",
  "Vehicles": {
    "drone_1": {
      "VehicleType": "SimpleFlight",
      "AutoCreate": true,
      "MoveMaxSpeed": 20,
      "LinearAccelMax": 20
    }
  }
}
```

### 1.4 Python Environment

Use the `openfly` conda environment which has `airsim 1.8.1` pre-installed:
```bash
conda activate openfly  # Python 3.10
```

---

## 2. Local Machine Setup

### 2.1 Python Version Requirement

AirSim's `msgpack-rpc-python` dependency requires **Python ≤ 3.12**.  
The `airsim` package **does not support Python 3.13+**.

**Check your Python version:**
```bash
python3 --version
```

If you have Python 3.13+ (e.g., via Homebrew), use pyenv:
```bash
pyenv install 3.10.13
pyenv local 3.10.13   # or use full path: ~/.pyenv/versions/3.10.13/bin/python3
```

### 2.2 Install Dependencies

```bash
# Use Python 3.10
~/.pyenv/versions/3.10.13/bin/pip install -r requirements.txt
~/.pyenv/versions/3.10.13/bin/pip install msgpack  # for airsim_rpc.py
```

> **Note:** Do NOT install the `airsim` pip package locally — AerialClaw uses its own
> pure-socket RPC implementation (`adapters/airsim_rpc.py`) which avoids all tornado/asyncio
> event loop conflicts.

### 2.3 Configure .env

```bash
cp .env.example .env
```

Edit `.env`:
```ini
SIM_ADAPTER=airsim
AIRSIM_HOST=127.0.0.1
AIRSIM_PORT=41451
AIRSIM_VEHICLE=drone_1
```

---

## 3. SSH Tunnel

AirSim's port 41451 only listens on `localhost` on the remote server.  
You must forward it via SSH tunnel:

```bash
# One-time setup: copy your SSH key to the server (avoids password prompts)
ssh-copy-id -p <PORT> user@<SERVER_IP>
# or manually: ssh-keygen && ssh -p <PORT> user@<SERVER_IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys" < ~/.ssh/id_rsa.pub

# Start persistent tunnel (background, auto-reconnect)
ssh -fNT \
    -L 41451:localhost:41451 \
    -p <PORT> \
    -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=5 \
    -o ExitOnForwardFailure=yes \
    user@<SERVER_IP>

# Verify
nc -zv 127.0.0.1 41451   # should say "succeeded"
```

**Kill tunnel when done:**
```bash
pkill -f "ssh.*41451"
```

---

## 4. Start AerialClaw

```bash
cd AerialClaw_2.0
~/.pyenv/versions/3.10.13/bin/python3 server.py
```

Expected startup log:
```
✅ AirSim connected: 127.0.0.1:41451, vehicles=['drone_1']
✅ Adapter airsim_simpleflight connected
AerialClaw console at http://localhost:5001
```

---

## 5. Known Pitfalls & Solutions

### Pitfall 1: `airsim` pip package fails on Python 3.13+

**Error:** `ModuleNotFoundError: No module named 'numpy'` or build failure  
**Cause:** `airsim 1.8.1` requires Python ≤ 3.12  
**Fix:** Use Python 3.10 via pyenv. AerialClaw's `airsim_rpc.py` does NOT require the `airsim` package.

---

### Pitfall 2: `RuntimeError: This event loop is already running`

**Error during connection:** `RuntimeError: This event loop is already running`  
**Cause:** Flask/gevent starts an asyncio loop; msgpackrpc tries to start another tornado ioloop  
**Fix:** `adapters/airsim_rpc.py` — pure socket implementation, zero event loop dependency.

---

### Pitfall 3: `tornado.platform.auto` missing in tornado 6.x

**Error:** `ModuleNotFoundError: No module named 'tornado.platform.auto'`  
**Cause:** Tornado 6 removed `tornado.platform.auto`; msgpackrpc still imports it  
**Fix:** Already handled in `airsim_rpc.py` — we don't use tornado at all.

---

### Pitfall 4: `BaseIOStream.__init__() got an unexpected keyword argument 'io_loop'`

**Same root cause as Pitfall 2/3.** Tornado 6 dropped the `io_loop` parameter.  
**Fix:** Same — `airsim_rpc.py` bypasses this entirely.

---

### Pitfall 5: AirSim binary has no execute permission

**Error:** `Permission denied` when running `start.sh`  
**Fix:**
```bash
chmod +x ~/code/openfly/envs/airsim/env_airsim_16/LinuxNoEditor/start.sh
chmod +x ~/code/openfly/envs/airsim/env_airsim_16/LinuxNoEditor/AirVLN/Binaries/Linux/AirVLN-Linux-Shipping
```

---

### Pitfall 6: `_try_connect_adapter()` not called

**Symptom:** Server starts but no AirSim connection attempt in logs  
**Cause:** `_try_connect_adapter()` was defined but never called in `_do_init()`  
**Fix:** Added explicit call in `server.py`:
```python
# In _do_init(), after state.initialized = True:
_try_connect_adapter()
_get_device_manager()
```

---

### Pitfall 7: SSH tunnel drops when using `expect` script

**Cause:** `expect` process exits after interaction, taking the tunnel with it  
**Fix:** Use `ssh -fNT` (fork to background, no command, no TTY) with SSH key auth.

---

### Pitfall 8: `sudo` password differs from login password

The server's sudo password may not match the SSH login password.  
**Workaround:** `Xvfb` not needed — use `-nullrhi` for headless AirSim instead.

---

## 6. Quick Reference

```bash
# ── On remote server ──────────────────────────────────────
# Start AirSim (env_airsim_16, headless)
nohup ~/code/openfly/envs/airsim/env_airsim_16/LinuxNoEditor/start.sh -nullrhi > /tmp/airsim.log 2>&1 &
# Check port
ss -tlnp | grep 41451
# Kill AirSim
pkill -f AirVLN-Linux-Shipping

# ── On local machine ──────────────────────────────────────
# Start SSH tunnel
ssh -fNT -L 41451:localhost:41451 -p <PORT> user@<IP>
# Start AerialClaw (Python 3.10)
cd AerialClaw_2.0 && ~/.pyenv/versions/3.10.13/bin/python3 server.py
# Kill tunnel
pkill -f "ssh.*41451"
```
