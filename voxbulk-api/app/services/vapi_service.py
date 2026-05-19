from __future__ import annotations


class VapiAdapter:
    """Legacy provider adapter.

    Vapi is intentionally not the active voice runtime. New outbound voice calls
    use Telnyx + Azure Speech + OpenAI.
    """

    def start_call(self, *, to_number: str, from_number: str | None = None) -> str:
        # TODO: Implement Vapi call initiation once API/auth is confirmed.
        return "not_implemented"

