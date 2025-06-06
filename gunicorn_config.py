# Gunicorn configuration file
import multiprocessing

# Bind to a Unix socket for local deployment or a TCP port for App Engine
import os
if 'PORT' in os.environ:
    # App Engine deployment - bind to the port specified by App Engine
    bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
else:
    # Local deployment - bind to a Unix socket
    bind = "unix:/tmp/avirta.sock"

# Number of worker processes
# For App Engine, use a fixed number of workers instead of calculating based on CPU count
if 'PORT' in os.environ:
    # App Engine deployment - use a fixed number of workers
    workers = 4
else:
    # Local deployment - calculate based on CPU count
    workers = multiprocessing.cpu_count() * 2 + 1

# Worker class
worker_class = "sync"

# Timeout for worker processes
timeout = 300

# Log settings
if 'PORT' in os.environ:
    # App Engine deployment - log to stdout/stderr
    accesslog = "-"  # stdout
    errorlog = "-"   # stderr
else:
    # Local deployment - log to files
    accesslog = "/var/log/avirta/access.log"
    errorlog = "/var/log/avirta/error.log"
loglevel = "info"

# Process name
proc_name = "avirta"

# Preload application code before forking workers
preload_app = True

# Increase buffer size for large headers
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190
