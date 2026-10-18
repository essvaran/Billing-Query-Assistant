"""Display masking for lists and dashboards. The full email is returned only on the single-ticket
detail call, to authenticated agents who need it to reply; everywhere else the customer is masked."""


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    host, _, tld = domain.rpartition(".")
    return f"{local[:1]}***@{host[:1]}***.{tld}"


def mask_name(name: str | None) -> str:
    if not name:
        return ""
    parts = name.split()
    return " ".join([parts[0]] + [p[:1] + "." for p in parts[1:]]) if len(parts) > 1 else parts[0][:1] + "."
