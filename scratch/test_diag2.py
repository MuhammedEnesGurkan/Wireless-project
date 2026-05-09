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

    res_ipt = await ssh.run_vm3("sudo iptables -L -n", check=False)
    print("VM3 iptables:\n", res_ipt.stdout)

    res_ovpn = await ssh.run_vm2("cat /etc/openvpn/client/client-udp.conf", check=False)
    print("VM2 OVPN conf:\n", res_ovpn.stdout)

    await ssh.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
