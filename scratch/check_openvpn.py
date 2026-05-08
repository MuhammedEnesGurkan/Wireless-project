import asyncio
from backend.services.ssh_manager import SshManager

async def main():
    mgr = SshManager()
    
    print("VM1:")
    try:
        res = await mgr.run_vm1("which openvpn && cat $(which openvpn) || echo 'not found'")
        print(res.stdout)
        print("STDERR:", res.stderr)
    except Exception as e:
        print("Error VM1:", e)

    print("VM2:")
    try:
        res = await mgr.run_vm2("which openvpn && cat $(which openvpn) || echo 'not found'")
        print(res.stdout)
        print("STDERR:", res.stderr)
    except Exception as e:
        print("Error VM2:", e)

    print("VM3:")
    try:
        res = await mgr.run_vm3("which openvpn && cat $(which openvpn) || echo 'not found'")
        print(res.stdout)
        print("STDERR:", res.stderr)
    except Exception as e:
        print("Error VM3:", e)

if __name__ == "__main__":
    asyncio.run(main())
