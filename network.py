import requests
from decimal import Decimal, InvalidOperation

RPC_TIMEOUT = 10

class Network:
    @staticmethod
    def rpc_call(port, method, params=None):
        """
        Executes a safe JSON-RPC POST call to the node.
        Returns the 'result' dictionary, or an error dictionary if the call fails.
        """
        try:
            r = requests.post(
                f"http://127.0.0.1:{port}/json_rpc",
                json={"jsonrpc": "2.0", "id": "0", "method": method, "params": params or {}},
                timeout=RPC_TIMEOUT
            )
            r.raise_for_status()
            return r.json().get("result", {})
        except Exception as e:
            return {"error": str(e)}
        
    @staticmethod
    def get_info(rpc_port):
        """Fetches node info using the generic rpc_call method."""
        return Network.rpc_call(rpc_port, "get_info")

    @staticmethod
    def get_public_ip():
        """Fetches the current public IP address from external services with a short timeout."""
        providers = [
            "https://api.ipify.org",
            "https://icanhazip.com",
            "https://v4.ident.me"
        ]
        for url in providers:
            try:
                response = requests.get(url, timeout=3)
                if response.status_code == 200:
                    return response.text.strip()
            except requests.RequestException:
                continue
        return "Unknown"

    @staticmethod
    def get_registration_cmd(selected_indices, amount, wallet):
        """Generates staking registration commands for the selected service nodes."""
        if not wallet.startswith("XEQM"):
            return ["Error: Wallet address must start with XEQM"]
        
        try:
            atomic = int(Decimal(str(amount).replace(",", ".")) * Decimal("1000000000"))
        except(InvalidOperation, TypeError, ValueError):
            return ["Error: Invalid amount format"]

        results = []
        for i in selected_indices:
            idx = i + 1
            rpc_port = 9231 + ((idx - 1) * 10) 
            
            res = Network.rpc_call(rpc_port, "get_service_node_registration_cmd", {
                "operator_cut": "10.0",
                "contributor_addresses": [wallet],
                "contributor_amounts": [atomic],
                "staking_requirement": 200000000000000
            })
            
            # Safe validation: check if 'error' key is present before reading data
            if isinstance(res, dict) and "error" in res:
                results.append(f"SN{idx:02d} Error: {res['error']}")
            elif isinstance(res, dict) and "registration_cmd" in res:
                results.append(f"SN{idx:02d}: {res['registration_cmd']}")
            else:
                results.append(f"SN{idx:02d} Error: Node returned an unexpected or empty response.")
                
        return results