"""Record package bytes, paths and symlink targets without following links."""

import hashlib
import os


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            content = os.readlink(path).encode()
            kind = b"link"
        elif path.is_file():
            content = path.read_bytes()
            kind = b"file"
        else:
            continue
        digest.update(kind + b"\0" + path.relative_to(root).as_posix().encode())
        digest.update(b"\0" + hashlib.sha256(content).digest())
    return digest.hexdigest()
