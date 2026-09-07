from __future__ import annotations

from hosted_push import HostedPushClient


def main() -> None:
    client = HostedPushClient()
    try:
        pairing = client.create_pairing_code()
        print()
        print("OverlookCam pairing code")
        print("------------------------")
        print(pairing["pairing_code"])
        print(f"Expires: {pairing['expires_at']}")
        print()
        print("Enter this code in the OverlookCam app. It can be used once.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
