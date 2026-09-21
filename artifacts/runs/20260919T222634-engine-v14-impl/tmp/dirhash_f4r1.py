import hashlib, pathlib
root = pathlib.Path('data/processed/halfday-bars-20260918')
h = hashlib.sha256()
n = 0
for p in sorted(root.rglob('*')):
    if p.is_file():
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode())
        h.update(hashlib.sha256(p.read_bytes()).digest())
        n += 1
print('files:', n, 'dir aggregate sha16:', h.hexdigest()[:16], '(prereg: c5ab29a09d2533eb)')
