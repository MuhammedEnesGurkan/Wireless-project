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

    res_log = await ssh.run_vm2("sudo cat /tmp/ovpn-udp.log | tail -n 25", check=False)
    print("VM2 OVPN Log:\n", res_log.stdout)

    res_ping = await ssh.run_vm1("ping -c 3 10.200.0.3", check=False)
    print("VM1 Ping VM3 WG:\n", res_ping.stdout, res_ping.stderr)

    await ssh.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
