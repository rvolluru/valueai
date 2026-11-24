"""Public Jouft handles, independent of identity-provider login names."""
import re
import unicodedata


class UsernameError(ValueError):
    pass


def default_username(first_name, last_name):
    value = '_'.join(str(v or '').strip() for v in (first_name, last_name) if str(v or '').strip())
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9_]+', '_', value).strip('_')[:40] or 'member'


def resolve_username(db, owner_subject, username, first_name, last_name):
    existing = db.fetchone(f'SELECT username FROM user_profiles WHERE owner_subject = {db.param}', (owner_subject,))
    requested = str(username or '').strip().removeprefix('@').lower()
    if not requested and existing and existing[0]:
        return existing[0]
    automatic = not requested
    candidate = requested or default_username(first_name, last_name)
    if not re.fullmatch(r'[a-z0-9_]{1,40}', candidate):
        raise UsernameError('Username must contain 1–40 letters, numbers, or underscores.')
    base = candidate
    suffix = 1
    while db.fetchone(f'SELECT owner_subject FROM user_profiles WHERE username = {db.param} AND owner_subject <> {db.param}', (candidate, owner_subject)):
        if not automatic:
            raise UsernameError('That username is already taken. Choose another.')
        suffix += 1
        tail = f'_{suffix}'
        candidate = base[:40-len(tail)] + tail
    return candidate
