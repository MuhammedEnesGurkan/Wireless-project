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

    print("=== FIXING VM3 IPTABLES ===")
    await ssh.run_vm3("sudo iptables -I INPUT 1 -p udp -m multiport --dports 51820,1194,500,4500 -j ACCEPT", check=False)
    await ssh.run_vm3("sudo iptables -I INPUT 1 -p tcp --dport 1194 -j ACCEPT", check=False)

    print("=== TESTING VM3 WG ===")
    await ssh.run_vm1("sudo systemctl restart wg-quick@wg0", check=False)
    await ssh.run_vm3("sudo wg-quick down wg0; sudo wg-quick up wg0", check=False)
    await asyncio.sleep(2)
    res_wg3 = await ssh.run_vm3("ping -c 3 10.200.0.1", check=False)
    print("VM3 WG Ping exit:", res_wg3.exit_status, "out:\n", res_wg3.stdout)
    res_wg_show = await ssh.run_vm3("sudo wg show", check=False)
    print("VM3 WG Show:\n", res_wg_show.stdout)

    print("=== FIXING OPENVPN MTU ===")
    mtu_conf = "tun-mtu 1200\\nmssfix 1160"
    
    # VM1 Server
    await ssh.run_vm1(f"sudo sed -i '/tun-mtu/d' /etc/openvpn/server/server-udp.conf", check=False)
    await ssh.run_vm1(f"sudo sed -i '/mssfix/d' /etc/openvpn/server/server-udp.conf", check=False)
    await ssh.run_vm1(f"echo -e '{mtu_conf}' | sudo tee -a /etc/openvpn/server/server-udp.conf", check=False)
    await ssh.run_vm1("sudo systemctl restart openvpn-server@server-udp", check=False)

    # VM2 Client
    await ssh.run_vm2(f"sudo sed -i '/tun-mtu/d' /etc/openvpn/client/client-udp.conf", check=False)
    await ssh.run_vm2(f"sudo sed -i '/mssfix/d' /etc/openvpn/client/client-udp.conf", check=False)
    await ssh.run_vm2(f"echo -e '{mtu_conf}' | sudo tee -a /etc/openvpn/client/client-udp.conf", check=False)

    print("=== TESTING VM2 OVPN UDP ===")
    await ssh.run_vm2("sudo pkill -x openvpn", check=False)
    await ssh.run_vm2("sudo /usr/sbin/openvpn --config /etc/openvpn/client/client-udp.conf --daemon", check=False)
    await asyncio.sleep(4)
    res_ovpn2 = await ssh.run_vm2("ping -c 3 10.8.0.1", check=False)
    print("VM2 OVPN Ping exit:", res_ovpn2.exit_status, "out:\n", res_ovpn2.stdout)

    await ssh.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
