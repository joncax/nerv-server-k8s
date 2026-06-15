import subprocess
import json
import datetime
import os

LOG_FILE = "/var/log/nerv/magi-agent.log"


def write_log(app: str, action: str, status: str, extra: dict = {}):
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "agent": "magi",
        "app": app,
        "action": action,
        "status": status,
        **extra,
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_command(cmd: list[str]):
    """Corre um comando e devolve (stdout, returncode)."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    return result.stdout, result.returncode


def run_command_stream(cmd: list[str]):
    """Corre um comando e faz yield linha a linha (para SSE)."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    for line in iter(process.stdout.readline, ""):
        yield line.rstrip()
    process.stdout.close()
    process.wait()
    return process.returncode


def get_local_digest(image: str) -> str | None:
    """Obtém o digest da imagem :latest actualmente no MicroK8s."""
    stdout, rc = run_command([
        "microk8s", "ctr", "images", "ls"
    ])
    if rc != 0:
        return None
    for line in stdout.splitlines():
        # procurar a linha exacta com :latest
        if f"{image}:latest" in line and "@sha256" not in line:
            parts = line.split()
            for part in parts:
                if part.startswith("sha256:"):
                    return part  # digest completo
    return None


def update_app(app_name: str, image: str, deployment: str, namespace: str):
    """
    Executa o processo completo de update de uma app.
    Faz yield de linhas de log para SSE streaming.
    """
    write_log(app_name, "update", "started")
    yield f"[magi] A iniciar update de {app_name}..."

    # 1. docker pull
    yield f"[magi] A fazer pull de {image}:latest..."
    pull_cmd = ["docker", "pull", f"{image}:latest"]
    for line in run_command_stream(pull_cmd):
        yield line

    # 2. docker save | microk8s ctr image import
    yield f"[magi] A importar imagem para o MicroK8s..."
    save_cmd = ["docker", "save", f"{image}:latest"]
    import_cmd = ["microk8s", "ctr", "image", "import", "-"]

    save_proc = subprocess.Popen(save_cmd, stdout=subprocess.PIPE)
    import_proc = subprocess.Popen(
        import_cmd,
        stdin=save_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    save_proc.stdout.close()
    import_out, _ = import_proc.communicate()
    for line in import_out.splitlines():
        yield line
    if import_proc.returncode != 0:
        write_log(app_name, "update", "failed", {"step": "import"})
        yield f"[magi] ERRO na importação da imagem."
        return

    # 3. rollout restart
    yield f"[magi] A reiniciar deployment {deployment}..."
    restart_cmd = [
        "microk8s", "kubectl", "rollout", "restart",
        f"deployment/{deployment}", "-n", namespace
    ]
    out, rc = run_command(restart_cmd)
    yield out.strip()

    if rc != 0:
        write_log(app_name, "update", "failed", {"step": "rollout"})
        yield f"[magi] ERRO no rollout restart."
        return

    # 4. aguardar rollout
    yield f"[magi] A aguardar rollout completo..."
    wait_cmd = [
        "microk8s", "kubectl", "rollout", "status",
        f"deployment/{deployment}", "-n", namespace,
        "--timeout=120s"
    ]
    for line in run_command_stream(wait_cmd):
        yield line

    write_log(app_name, "update", "success")
    yield f"[magi] ✓ Update de {app_name} concluído com sucesso."
