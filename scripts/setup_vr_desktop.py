#!/usr/bin/env python3
"""
Set up vr-desktop: install Docker Desktop, enable WSL2, install Ollama model.
Run from thing1 after GGUF transfer is complete.
"""
import paramiko
import time

VR_HOST = "100.110.246.22"
VR_USER = "sshclaude1"
VR_PASS = "201388Ter"
OLLAMA_EXE = "C:\\Users\\sshclaude1\\AppData\\Local\\Programs\\Ollama\\ollama.exe"


def run(client, cmd, timeout=30, label=None):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="ignore").strip()
    err = stderr.read().decode(errors="ignore").strip()
    if label:
        print(f"  {label}: {(out or err or '(ok)')[:300]}")
    return out, err


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VR_HOST, username=VR_USER, password=VR_PASS, timeout=20)
    print("Connected to vr-desktop")

    # 1. Enable WSL2 features (needed for Docker Desktop)
    print("\n[1/4] Enabling WSL2 + VirtualMachinePlatform...")
    run(client,
        "dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart",
        timeout=60, label="WSL")
    run(client,
        "dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart",
        timeout=60, label="VMP")

    # 2. Install Docker Desktop via winget (background)
    print("\n[2/4] Starting Docker Desktop install (background)...")
    run(client,
        'start /B cmd /C "winget install Docker.DockerDesktop --silent --accept-package-agreements --accept-source-agreements > C:\\pmcore-models\\docker_install.log 2>&1"',
        timeout=10, label="Docker winget")

    # 3. Register Ollama model (after GGUF transfer completes)
    print("\n[3/4] Registering PMCommunicator in Ollama...")
    print("  Waiting for GGUF file...")
    for i in range(30):
        out, _ = run(client,
                     "dir C:\\pmcore-models\\pmcommunicator.Q8_0.gguf 2>nul | findstr gguf",
                     timeout=10)
        if "gguf" in out.lower():
            print("  GGUF file present, registering model...")
            run(client,
                f'"{OLLAMA_EXE}" create pmcommunicator -f C:\\pmcore-models\\Modelfile',
                timeout=120, label="ollama create")
            break
        print(f"  Waiting... ({i+1}/30)")
        time.sleep(10)
    else:
        print("  GGUF not found after 5 min — run register_model.bat manually after transfer completes")

    # 4. Start ollama serve
    print("\n[4/4] Starting Ollama serve...")
    run(client,
        f'start /B "" "{OLLAMA_EXE}" serve',
        timeout=10, label="serve")
    time.sleep(5)
    out, _ = run(client, "netstat -an | findstr :11434", timeout=10)
    print(f"  Port 11434: {out[:100] or 'not yet (may need desktop session)'}")

    client.close()
    print("\nDone. vr-desktop setup complete.")
    print("NOTE: A reboot may be needed for WSL2 + Docker to fully activate.")


if __name__ == "__main__":
    main()
