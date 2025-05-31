# Gunicorn configuration file
import multiprocessing

# Bind to a Unix socket that Nginx can communicate with
bind = "unix:/tmp/avirta.sock"

# Number of worker processes
workers = multiprocessing.cpu_count() * 2 + 1

# Worker class
worker_class = "sync"

# Timeout for worker processes
timeout = 120

# Log settings
accesslog = "/var/log/avirta/access.log"
errorlog = "/var/log/avirta/error.log"
loglevel = "info"

# Process name
proc_name = "avirta"

# Preload application code before forking workers
preload_app = True