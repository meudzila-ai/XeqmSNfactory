import subprocess
import os
import yaml
import psutil   # type: ignore

class DockerManager:
    IMAGE = "ghcr.io/xeqmlabs/xeqm-node:latest"

    # =========================================================================
    # 1. OS & SYSTEM HELPER METHODS
    # =========================================================================
    @staticmethod
    def _get_creationflags():
        """Returns CREATE_NO_WINDOW flag only if running on Windows OS."""
        if os.name == 'nt':
            return getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        return 0

    # =========================================================================
    # 2. DOCKER CONTAINER MONITORING
    # =========================================================================
    @staticmethod
    def list_running_containers():
        """
        Returns a list of running container names.
        Protected with a timeout to prevent hanging if Docker Daemon freezes.
        """
        try:
            res = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                creationflags=DockerManager._get_creationflags(),
                timeout=5
            )
            return res.stdout.splitlines() if res.returncode == 0 else []
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            print(f"⚠️ Docker PS warning/error: {e}")
            return []
    
    # =========================================================================
    # 3. RESOURCE & RAM VALIDATION
    # =========================================================================
    @staticmethod
    def validate_ram_safety(selected_indices):
        """
        Validates whether the system has enough total RAM to safely host the selected number of nodes.
        Returns (is_safe, error_message)
        """
        total_nodes = len(selected_indices)
        if total_nodes == 0:
            return True, ""

        vm = psutil.virtual_memory()
        system_ram_gb = vm.total / (1024 ** 3)

        # Consistent memory allocation profile across validation and docker compose creation
        if system_ram_gb <= 10:
            required_per_node = 1.5   # 1536M
        elif system_ram_gb <= 18:
            required_per_node = 2.0   # 2048M
        else:
            required_per_node = 2.15  # 2200M

        total_required_ram = total_nodes * required_per_node
        safe_margin = 3.5  # Preserved RAM buffer for Windows OS & background services
        
        if (system_ram_gb - total_required_ram) < safe_margin:
            max_safe_nodes = max(0, int((system_ram_gb - safe_margin) // required_per_node))
            
            error_msg = (
                f"Insufficient System RAM capacity!\n\n"
                f"Deploying {total_nodes} nodes requires around {total_required_ram:.1f} GB of RAM allocation.\n"
                f"Your PC total RAM: {system_ram_gb:.1f} GB (System requires {safe_margin} GB margin).\n\n"
                f"Based on your computer's specifications, you can safely deploy a maximum of {max_safe_nodes} node(s).\n"
                f"Please select fewer nodes to avoid system crash."
            )
            return False, error_msg

        return True, ""

    # =========================================================================
    # 4. DOCKER COMPOSE CONFIGURATION GENERATOR
    # =========================================================================
    @staticmethod
    def create_compose(base_path, selected_indices, public_ip, max_out_peers=16, max_in_peers=0):
        """Generates a docker-compose.yml file with resource allocation and peer limits."""
        if not selected_indices:
            return False

        vm = psutil.virtual_memory()
        system_ram_gb = vm.total / (1024 ** 3)

        # Synchronized memory limits matching validate_ram_safety
        if system_ram_gb <= 10:
            mem_limit = "1536M"
            cpu_quota = 50000
        elif system_ram_gb <= 18:
            mem_limit = "2048M"
            cpu_quota = 75000
        else:
            mem_limit = "2200M"
            cpu_quota = 100000

        services = {}
        for i in selected_indices:
            idx = i + 1
            name = f"sn{idx:02d}"
            
            p2p = 9230 + ((idx - 1) * 10)
            rpc = 9231 + ((idx - 1) * 10)
            quo = 9232 + ((idx - 1) * 10)

            l_path_clean = os.path.normpath(os.path.join(base_path, "data", name)).replace("\\", "/")
            os.makedirs(l_path_clean, exist_ok=True)

            services[name] = {
                "image": DockerManager.IMAGE,
                "container_name": name,
                "restart": "unless-stopped",
                "ports": [
                    f"127.0.0.1:{rpc}:{rpc}/tcp",  
                    f"0.0.0.0:{p2p}:{p2p}/tcp",
                    f"0.0.0.0:{quo}:{quo}/tcp",
                    f"0.0.0.0:{quo}:{quo}/udp"
                ],
                "cpu_period": 100000,
                "cpu_quota": cpu_quota,
                "mem_limit": mem_limit,
                "volumes": [f"{l_path_clean}:/data"],
                "command": (
                    f"--service-node --data-dir=/data "
                    f"--p2p-bind-port={p2p} "
                    f"--rpc-admin=0.0.0.0:{rpc} "
                    f"--confirm-external-bind "
                    f"--service-node-public-ip={public_ip} "
                    f"--quorumnet-port={quo} "
                    f"--add-priority-node=seed-1.xeqmlabs.com:9230 "
                    f"--out-peers={max_out_peers} "
                    f"--in-peers={max_in_peers} "
                    f"--non-interactive --log-level=0"
                )
            }
        
        try:
            compose_path = os.path.join(base_path, "docker-compose.yml")
            with open(compose_path, "w", encoding="utf-8") as f:
                yaml.dump({"services": services}, f, sort_keys=False)
            return True
        except (IOError, OSError, yaml.YAMLError) as e:
            print(f"❌ ERROR: Failed to create docker-compose.yml: {e}")
            return False

    # =========================================================================
    # 5. DOCKER SERVICE EXECUTION COMMANDS
    # =========================================================================
    @staticmethod
    def compose_up(path):
        """Starts Docker nodes in background with timeout protection."""
        try:
            return subprocess.run(
                ["docker", "compose", "up", "-d", "--remove-orphans", "--force-recreate"],
                cwd=path,
                capture_output=True,
                creationflags=DockerManager._get_creationflags(),
                timeout=120  # Protection against hanging during image downloads
            )
        except subprocess.TimeoutExpired:
            class DummyResult:
                returncode = 1
                stderr = b"Docker compose up command timed out."
            return DummyResult()

    @staticmethod
    def compose_down(path):
        """Stops Docker nodes with timeout protection."""
        try:
            return subprocess.run(
                ["docker", "compose", "down"],
                cwd=path,
                capture_output=True,
                creationflags=DockerManager._get_creationflags(),
                timeout=60
            )
        except subprocess.TimeoutExpired:
            class DummyResult:
                returncode = 1
                stderr = b"Docker compose down command timed out."
            return DummyResult()