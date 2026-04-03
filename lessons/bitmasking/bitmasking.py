READ, WRITE, EXECUTE = 1 << 0, 1 << 1, 1 << 2

perm = 0
perm |= READ | EXECUTE
print(f"Set READ+EXEC -> {perm:03b}")

perm &= ~EXECUTE
print(f"Clear EXECUTE -> {perm:03b}")

perm ^= WRITE
print(f"Toggle WRITE -> {perm:03b}")

print("Readable?", bool(perm & READ))
print("Writable?", bool(perm & WRITE))
print("Executable?", bool(perm & EXECUTE))
