import asyncio
from backend.services.ssh_manager import get_ssh_manager
from backend.services.runtime_config import update_runtime_config

async def main():
    update_runtime_config(
        vm1_use_password_auth=True, vm1_ssh_password="12345678",
        vm2_use_password_auth=True, vm2_ssh_password="12345678",
        vm3_use_password_auth=True, vm3_ssh_password="1905"
    )
    ssh = get_ssh_manager()

    print("=== VM2 DIAGNOSTICS ===")
    res_tc2 = await ssh.run_vm2("tc qdisc show dev tailscale0", check=False)
    print("VM2 tc:\n", res_tc2.stdout)
    
    res_fw2 = await ssh.run_vm2("sudo ufw status", check=False)
    print("VM2 ufw:\n", res_fw2.stdout)

    print("=== VM3 DIAGNOSTICS ===")
    res_tc3 = await ssh.run_vm3("tc qdisc show dev tailscale0", check=False)
    print("VM3 tc:\n", res_tc3.stdout)

    res_fw3 = await ssh.run_vm3("sudo ufw status", check=False)
    print("VM3 ufw:\n", res_fw3.stdout)

    await ssh.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
