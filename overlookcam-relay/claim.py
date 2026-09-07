from __future__ import annotations

from hosted_push import HostedPushClient


def main() -> None:
    client = HostedPushClient()
    try:
        claim = client.create_claim_code()
        print()
        print("OverlookCam account claim code")
        print("----------------------------")
        print(claim["claim_code"])
        print(f"Expires: {claim['expires_at']}")
        print()
        print("Sign in at https://account.overlookcam.com, choose Add another relay, and enter this code.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
