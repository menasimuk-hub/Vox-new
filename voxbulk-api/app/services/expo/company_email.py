"""Company vs free-consumer email domain checks for Expo signup trial."""

from __future__ import annotations

# Exact free / consumer mailbox domains (lowercase).
FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "outlook.co.uk",
        "hotmail.com",
        "hotmail.co.uk",
        "hotmail.fr",
        "hotmail.de",
        "hotmail.it",
        "hotmail.es",
        "live.com",
        "live.co.uk",
        "msn.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
        "aol.com",
        "aol.co.uk",
        "mail.com",
        "email.com",
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "gmx.at",
        "gmx.ch",
        "yandex.com",
        "yandex.ru",
        "ya.ru",
        "yahoo.com",
        "yahoo.co.uk",
        "yahoo.fr",
        "yahoo.de",
        "yahoo.it",
        "yahoo.es",
        "yahoo.ca",
        "yahoo.com.au",
        "ymail.com",
        "rocketmail.com",
        "zoho.com",
        "zohomail.com",
        "fastmail.com",
        "fastmail.fm",
        "tutanota.com",
        "tuta.io",
        "mail.ru",
        "inbox.com",
        "hey.com",
        "qq.com",
        "163.com",
        "126.com",
        "rediffmail.com",
        "btinternet.com",
        "btopenworld.com",
        "sky.com",
        "virginmedia.com",
        "ntlworld.com",
        "talktalk.net",
        "orange.fr",
        "wanadoo.fr",
        "free.fr",
        "laposte.net",
        "web.de",
        "t-online.de",
        "libero.it",
        "virgilio.it",
        "seznam.cz",
        "wp.pl",
        "o2.pl",
        "interia.pl",
        "naver.com",
        "daum.net",
        "hanmail.net",
    }
)

# First DNS label of consumer providers that use many ccTLDs (yahoo.co.jp, hotmail.nl, …).
_FREE_FIRST_LABELS: frozenset[str] = frozenset(
    {
        "yahoo",
        "ymail",
        "rocketmail",
        "hotmail",
        "gmx",
        "yandex",
        "aol",
        "protonmail",
    }
)


def extract_email_domain(email: str | None) -> str:
    raw = str(email or "").strip().lower()
    if "@" not in raw:
        return ""
    domain = raw.rsplit("@", 1)[-1].strip().rstrip(".")
    if not domain or " " in domain or "/" in domain:
        return ""
    return domain


def is_free_email_domain(domain: str | None) -> bool:
    d = str(domain or "").strip().lower().rstrip(".")
    if not d:
        return True
    if d in FREE_EMAIL_DOMAINS:
        return True
    first = d.split(".", 1)[0]
    if first in _FREE_FIRST_LABELS:
        return True
    return False


def is_company_email(email: str | None) -> bool:
    domain = extract_email_domain(email)
    if not domain:
        return False
    return not is_free_email_domain(domain)
