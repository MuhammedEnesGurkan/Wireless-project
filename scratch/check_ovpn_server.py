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

    res_log1 = await ssh.run_vm1("sudo journalctl -u openvpn-server@server-udp -n 30", check=False)
    print("VM1 OVPN Server Log:\n", res_log1.stdout)

    print("=== DUMPING WG0 on VM3 ===")
    dump_task = asyncio.create_task(ssh.run_vm3("sudo tcpdump -i wg0 -n -c 5", check=False))
    await asyncio.sleep(2)
    await ssh.run_vm3("ping -c 3 10.200.0.1", check=False)
    
    try:
        res_dump = await asyncio.wait_for(dump_task, timeout=5)
        print("VM3 WG0 Dump:\n", res_dump.stdout)
    except asyncio.TimeoutError:
        print("VM3 WG0 Dump timeout")
        await ssh.run_vm3("sudo pkill -x tcpdump", check=False)

    await ssh.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
