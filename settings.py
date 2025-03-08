from decouple import config

# ... other settings ...

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')
print("ALLOWED_HOSTS:", ALLOWED_HOSTS)  # Temporary debug line 