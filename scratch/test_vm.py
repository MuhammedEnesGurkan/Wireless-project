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

    print("=== VM1 STATUS ===")
    res1 = await ssh.run_vm1("sudo wg show", check=False)
    print("wg show:\n", res1.stdout)

    res2 = await ssh.run_vm1("sudo systemctl status openvpn-server@server-udp | head -n 15", check=False)
    print("ovpn status:\n", res2.stdout.encode('ascii', 'ignore').decode('ascii'))

    res3 = await ssh.run_vm1("sudo netstat -tuln | grep -E '51820|1194'", check=False)
    print("netstat:\n", res3.stdout)
    
    print("\nStarting wg on VM1...")
    res_start = await ssh.run_vm1("sudo systemctl restart wg-quick@wg0", check=False)
    print("start wg exit:", res_start.exit_status, "err:", res_start.stderr)

    res4 = await ssh.run_vm1("sudo wg show", check=False)
    print("wg show after start:\n", res4.stdout)

    print("\nStarting OpenVPN UDP on VM1...")
    res_ovpn_start = await ssh.run_vm1("sudo systemctl restart openvpn-server@server-udp", check=False)
    print("start ovpn exit:", res_ovpn_start.exit_status, "err:", res_ovpn_start.stderr)
    
    res5 = await ssh.run_vm1("sudo systemctl status openvpn-server@server-udp | head -n 15", check=False)
    print("ovpn status after start:\n", res5.stdout.encode('ascii', 'ignore').decode('ascii'))

    await ssh.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
