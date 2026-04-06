#!/usr/bin/env python3
"""Write Modelfile and setup scripts to vr-desktop via SFTP."""
import paramiko

MODELFILE = (
    "FROM C:\\\\pmcore-models\\\\pmcommunicator.Q8_0.gguf\n"
    "\n"
    'SYSTEM """You are PMCommunicator, an expert project manager and communications specialist. '
    "Generate professional, stakeholder-ready project communications based on the provided "
    "project context. Be specific - use the actual project name, numbers, and timeline. "
    'Write in clear business English. Output only the communication document itself."""\n'
    "\n"
    "PARAMETER temperature 0.3\n"
    "PARAMETER top_p 0.9\n"
    "PARAMETER top_k 40\n"
    "PARAMETER repeat_penalty 1.1\n"
    "PARAMETER num_predict 800\n"
)

REGISTER_BAT = (
    "@echo off\n"
    "echo Setting up PMCommunicator in Ollama...\n"
    'set OLLAMA=C:\\Users\\sshclaude1\\AppData\\Local\\Programs\\Ollama\\ollama.exe\n'
    '"%OLLAMA%" create pmcommunicator -f C:\\pmcore-models\\Modelfile\n'
    "echo.\n"
    "echo Done! Test with:\n"
    "echo   ollama run pmcommunicator\n"
    "pause\n"
)

transport = paramiko.Transport(("100.110.246.22", 22))
transport.connect(username="sshclaude1", password="201388Ter")
sftp = paramiko.SFTPClient.from_transport(transport)

with sftp.open("/C:/pmcore-models/Modelfile", "w") as f:
    f.write(MODELFILE)
print("Modelfile written")

with sftp.open("/C:/pmcore-models/register_model.bat", "w") as f:
    f.write(REGISTER_BAT)
print("register_model.bat written")

sftp.close()
transport.close()
print("Done.")
